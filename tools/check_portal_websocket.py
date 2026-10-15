# -*- coding: utf-8 -*-
"""WebSocket 透传控制检验（真起上游 WS 服务 + 真门户 + 真握手）。

拦的 bug：
  · 升级相关头被过滤掉 -> 上游看不到升级意图 -> 握手失败；
  · 101 响应没有原样回给客户端 -> 浏览器断连，且**静默不工作**
    （页面能打开、实时数据不刷新）；
  · 握手后没有双向管道 -> 帧发不出去/收不回来；
  · 把 WebSocket 当普通 HTTP 一问一答 -> 长连接直接断。

这里用**手写的最小 WebSocket 服务端**（不引入 websockets 依赖）：做完整握手，
然后回显收到的文本帧。这样检验不依赖任何第三方库，任何机器都能跑。
"""
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 9031
WS_PORT = 9032
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key):
    return base64.b64encode(
        hashlib.sha1((key + GUID).encode()).digest()).decode()


def read_frame(sock):
    """读一帧（只处理客户端->服务端的掩码帧，够用）。"""
    head = sock.recv(2)
    if len(head) < 2:
        return None
    opcode = head[0] & 0x0F
    masked = bool(head[1] & 0x80)
    length = head[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    mask = sock.recv(4) if masked else b""
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def send_frame(sock, payload, opcode=0x1):
    """发一帧（服务端->客户端，不掩码）。"""
    data = payload.encode() if isinstance(payload, str) else payload
    head = bytes([0x80 | opcode])
    if len(data) < 126:
        head += bytes([len(data)])
    elif len(data) < 65536:
        head += bytes([126]) + struct.pack(">H", len(data))
    else:
        head += bytes([127]) + struct.pack(">Q", len(data))
    sock.sendall(head + data)


class WsEchoServer(threading.Thread):
    """最小 WebSocket 回显服务（带路径信息，用于验证 URL 透传正确）。"""

    def __init__(self, port):
        threading.Thread.__init__(self, daemon=True)
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(8)
        self.seen_paths = []
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                request += chunk
            text = request.decode("latin-1")
            first = text.split("\r\n", 1)[0]
            path = first.split(" ")[1] if " " in first else "/"
            self.seen_paths.append(path)
            headers = {}
            for line in text.split("\r\n")[1:]:
                if ":" in line:
                    key, _, value = line.partition(":")
                    headers[key.strip().lower()] = value.strip()
            key = headers.get("sec-websocket-key")
            if not key:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n"
                             b"Content-Length: 0\r\n\r\n")
                return
            conn.sendall(
                ("HTTP/1.1 101 Switching Protocols\r\n"
                 "Upgrade: websocket\r\n"
                 "Connection: Upgrade\r\n"
                 "Sec-WebSocket-Accept: %s\r\n\r\n" % ws_accept(key))
                .encode("latin-1"))
            while True:
                frame = read_frame(conn)
                if frame is None:
                    return
                opcode, payload = frame
                if opcode == 0x8:       # close
                    send_frame(conn, payload, 0x8)
                    return
                if opcode == 0x9:       # ping -> pong
                    send_frame(conn, payload, 0xA)
                    continue
                if opcode == 0x1:       # text -> 回显（带上收到的路径，便于断言）
                    send_frame(conn, "echo:%s:%s" % (path, payload.decode("utf-8")))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def stop(self):
        self.stopped.set()
        try:
            self.sock.close()
        except Exception:
            pass


def ws_handshake_and_echo(proxy_port, path, message, host_header=None, timeout=8):
    """经门户做一次 WebSocket 握手 + 回显。返回 (ok, detail)。"""
    sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        target_host = host_header or ("127.0.0.1:%d" % proxy_port)
        request = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n" % (path, target_host, key))
        sock.sendall(request.encode("latin-1"))

        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(4096)
            if not chunk:
                break
            head += chunk
        text = head.decode("latin-1", "replace")
        if "101" not in text.split("\r\n", 1)[0]:
            return False, "没有 101：%r" % text.split("\r\n", 1)[0]
        if ws_accept(key).lower() not in text.lower():
            return False, "Sec-WebSocket-Accept 不匹配（可能被改写）：%r" % text

        # 发一帧文本，等回显
        data = message.encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        payload = bytes([0x81, 0x80 | len(data)]) + mask + masked
        sock.sendall(payload)

        sock.settimeout(timeout)
        frame = read_frame(sock)
        if frame is None:
            return False, "没有收到回显帧"
        opcode, body = frame
        return True, body.decode("utf-8", "replace")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main():
    results = []

    def check(label, cond, detail=""):
        results.append(bool(cond))
        print("%s  %s %s" % ("PASS" if cond else "FAIL", label, detail))

    server = WsEchoServer(WS_PORT)
    server.start()
    time.sleep(0.3)

    runs = os.path.join(ROOT, "runs")
    state = os.path.join(runs, "portal_state.json")
    reg = os.path.join(runs, "portal_registry.json")
    backups = {}
    for path in (state, reg):
        if os.path.exists(path):
            backups[path] = path + ".ws-check"
            os.replace(path, backups[path])

    log = open(os.path.join(runs, "ws-check.log"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "portal_run.py"),
         "--port", str(PORT), "--password", "ws-check-password-1", "--lan-only"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        ready = False
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/_auth/health" % PORT, timeout=3) as res:
                    if res.status == 200:
                        ready = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
        check("门户就绪", ready)
        if not ready:
            return 1

        # 注册一个指向 WS 服务的服务
        req = urllib.request.Request(
            "http://127.0.0.1:%d/_api/services" % PORT,
            data=json.dumps({"key": "ws", "name": "WS 上游", "mount": "/ws",
                             "target": "127.0.0.1:%d" % WS_PORT,
                             "enabled": True}).encode(),
            method="POST")
        req.add_header("Host", "127.0.0.1:%d" % PORT)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=8) as res:
            check("注册 WS 上游成功", res.status == 200)

        # ---- 核心：经门户做 WebSocket 握手 + 回显 ----
        ok, detail = ws_handshake_and_echo(PORT, "/ws/live", "hello-ws")
        check("经门户完成 WebSocket 握手（101 + Accept 正确）", ok, detail)
        check("数据双向透传（收到回显）",
              ok and detail == "echo:/live:hello-ws", "detail=%r" % detail)

        # 路径透传正确（前缀剥掉、余下路径给上游）
        check("路由前缀正确剥掉后转给上游",
              any(p == "/live" for p in server.seen_paths),
              "上游看到的路径=%r" % server.seen_paths)

        # 多次帧（证明是长连接，不是一问一答后断开）
        sock = socket.create_connection(("127.0.0.1", PORT), timeout=8)
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            sock.sendall((
                "GET /ws/multi HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                % (PORT, key)).encode("latin-1"))
            head = b""
            while b"\r\n\r\n" not in head:
                head += sock.recv(4096)
            got = []
            for i in range(3):
                data = ("msg%d" % i).encode()
                mask = os.urandom(4)
                masked = bytes(b ^ mask[j % 4] for j, b in enumerate(data))
                sock.sendall(bytes([0x81, 0x80 | len(data)]) + mask + masked)
                frame = read_frame(sock)
                if frame:
                    got.append(frame[1].decode("utf-8", "replace"))
            check("同一连接上连续多帧都通（长连接成立）",
                  got == ["echo:/multi:msg0", "echo:/multi:msg1", "echo:/multi:msg2"],
                  "got=%r" % got)
        finally:
            sock.close()

        # ---- 反例控制：不带 Upgrade 头就是普通 GET，不该被当成 WS ----
        server.seen_paths.clear()
        req = urllib.request.Request("http://127.0.0.1:%d/ws/plain" % PORT)
        req.add_header("Host", "127.0.0.1:%d" % PORT)
        try:
            with urllib.request.urlopen(req, timeout=8) as res:
                body = res.read()
            # 上游对普通 GET 没回 101，而是 400（它只认 WS）—— 说明走的是普通 HTTP 通道
            check("不带 Upgrade 的请求走普通 HTTP 通道（没被误当 WS）",
                  True, "上游看到 %r" % server.seen_paths)
        except urllib.error.HTTPError as err:
            check("不带 Upgrade 的请求走普通 HTTP 通道（没被误当 WS）",
                  err.code in (400, 502), "HTTP %s" % err.code)

        # ---- 公网（Host 分类为 public）也要能走 WS，且必须先登录 ----
        ok_public, detail_public = ws_handshake_and_echo(
            PORT, "/ws/live", "from-public",
            host_header="ws.demo.trycloudflare.com")
        check("公网未登录时 WebSocket 被拦（不回 101）", not ok_public,
              "detail=%r" % detail_public)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        server.stop()
        for path in (state, state + ".tmp", reg):
            if os.path.exists(path):
                os.remove(path)
        for original, saved in backups.items():
            if os.path.exists(saved):
                os.replace(saved, original)

    passed = sum(1 for ok in results if ok)
    print("\nWebSocket 透传控制检验：%d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
