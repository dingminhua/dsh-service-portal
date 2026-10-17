# -*- coding: utf-8 -*-
"""临时「状态目录」：给需要起真门户的检验用，**不碰用户真实数据**。

为什么需要这个模块
------------------
`tools/portal_run.py` 把状态写在 `runs/`（`portal_state.json`、`portal_registry.json`、
口令副本）。里面有**用户真实的东西**：局域网口令、用户在控制台加的服务节点、
上次是"主动停止"还是崩溃退出。

早先几个检验的做法是「把用户的状态文件 os.replace 走 → 跑测试 → 跑完再换回来」。
这次真出事了：`test_lan_switch.py` 起停了一次门户，用户的状态文件就被写成
`stopped_clean: true`，他打开设置页看到的是「门户未启动」—— 一个测试把用户
正在用的门户"关掉"了。而且这种备份/还原在**测试中途异常退出**时（KeyboardInterrupt、
断言失败、进程被杀）也根本不会执行，等于把用户状态留在半残的中间态。

正确做法：门户本来就支持 `PORTAL_RUNS_DIR` 顶掉状态目录（见 portal_run.py 顶部
的注释）。检验把状态目录指向 mkdtemp 出来的临时目录，用户的 runs/ 从头到尾
**没人打开过**，也就不存在"还原失败"这种状态。

用法
----
    with isolated_runs() as runs:
        proc = subprocess.Popen([...], env=portal_env(runs), ...)

`portal_env()` 返回的是基于当前环境**复制**的一份（不改父进程的 os.environ），
所以同一个 shell 里连跑多个检验也不会互相串。
"""
import os
import shutil
import tempfile
from contextlib import contextmanager


@contextmanager
def isolated_runs():
    """产出一个临时的 runs 目录；离开 with 时整棵删掉。"""
    path = tempfile.mkdtemp(prefix="portal-runs-")
    try:
        # portal_run.py 会自己建 portal_logs/，这里不预建，省得两边规则不一致
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def portal_env(runs, base=None):
    """拼出给 portal_run.py 子进程用的环境变量（复制，不改调用方）。"""
    env = dict(base if base is not None else os.environ)
    env["PORTAL_RUNS_DIR"] = runs
    return env
