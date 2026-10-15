<p align="center">
  <img src="icons/dsh-service-portal-64.png" width="64" alt="dsh-service-portal" />
</p>

<h1 align="center">dsh-service-portal</h1>

<p align="center"><b>One random domain + one random password to expose your local services on demand.</b></p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#service-manifest">Service manifest</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="https://github.com/dingminhua/dsh-service-portal/issues">Issues</a>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/dsh-service-portal"><img src="https://img.shields.io/npm/v/dsh-service-portal?style=flat-square&label=npm&color=cb3837" alt="npm version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/dingminhua/dsh-service-portal?style=flat-square" alt="MIT license"></a>
</p>

**dsh-service-portal (Service Portal)** is a [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/deepseek-harness) plugin.
It exposes **any local service** to the public internet on demand: `cloudflared` creates a **random domain**,
an **Basic Auth** proxy guards it with a **random password**, and a settings-page toggle shows the URL
and credentials.

It originally lived inside `ld-rl-poker` (to put its training dashboard / model viewer online), but the
portal itself has nothing to do with poker — **any local service** can use the same
"one domain + one password + on-demand mount" pattern.

## Features

- **One-click exposure** — the settings page starts the service → auth proxy → tunnel, no manual steps.
- **Random domain + random password** — both change on every start; the password is written to a local
  credentials file only (plain text, gitignored, never share it).
- **Two shapes** — one random domain per service, or **one domain + path prefix**
  (`https://<random>/train/`).
- **Manifest-driven** — write `services.json` to expose any service without touching code; an empty
  manifest falls back to the built-in default (ld-rl-poker's two GUIs, backwards compatible).
- **Control checks** (house rule) — 35 tunnel-auth, 10 domain, 23+23 host-metrics, 26 plugin-contract
  checks; **a missing dependency must "skip and return 2", never silently pass**.
- **Host metrics** — CPU / memory / VRAM / GPU utilization; unreadable values render "—", never a fake 0.

## How it works

```
https://<random>.trycloudflare.com   (cloudflared quick tunnel, new domain every start)
              |
              v
127.0.0.1:<proxyPort>  tools/tunnel_auth.py (Basic Auth, new password every start)
              |
              v
127.0.0.1:<guiPort>    your local service (GUI / Ollama / any HTTP service)
```

## Installation

### Via npm (after publish)

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add dsh-service-portal
```

### Via link (during development)

```powershell
$dsh = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add "link:D:/DshProject/dsh-service-portal"
```

Restart DSH after installing (the bundle loads in the host process).

## Configuration (DSH settings page)

| Field | Default | Description |
| :--- | :--- | :--- |
| `infraPath` | this repo root | Infrastructure repo: contains `tools/` and `runs/` (tunnel/proxy/credentials) |
| `repoPath` | `D:\DshProject\ld-rl-poker` | Host repo root: where the exposed services live |
| `pythonPath` | empty | Interpreter for services; auto-selects `.venv313` → `.runtime` → PATH |
| `webEnabled` | `true` | Mount the `/service-portal/api` routes |

All four are `.volatile()`: changes apply immediately without remounting the plugin.

## HTTP API

Mounted on the host webServer (`prefix` routes under `/service-portal/api`):

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/service-portal/api/status` | Current state: running, mode, URL, password, endpoints |
| GET | `/service-portal/api` | Same as `/status` |
| POST | `/service-portal/api/start` | Start (body optional `{"singleDomain": true}`, default single-domain+paths) |
| POST | `/service-portal/api/stop` | Stop |

Unknown sub-paths return **404** (no status fallback — a mistyped path must not "look usable").

## Service manifest

With no configuration the built-in manifest is used (= ld-rl-poker's two GUIs). To expose other
services, write `services.json`:

```json
{
  "hostRepo": "D:\\DshProject\\ld-rl-poker",
  "services": [
    {"key": "train",  "script": "gui/server.py",        "guiPort": 8810,
     "proxyPort": 8890, "name": "训练配置台", "mount": "train"},
    {"key": "ollama", "script": "serve.py",             "guiPort": 11434,
     "proxyPort": 11499, "name": "Ollama",   "mount": "ollama"}
  ]
}
```

Priority: `--services <json>` > `$SERVICE_PORTAL_SERVICES` > `./services.json` > built-in manifest.

- `hostRepo`: host repo root the service scripts are relative to;
- `script` / `guiPort`: the service to launch and its port;
- `proxyPort`: per-service auth proxy port in multi-domain mode;
- `mount`: path prefix in single-domain mode (`/train/`).

## Tools (usable without the plugin)

| File | Purpose |
| :--- | :--- |
| `tools/start_public_gui.py` | One-click launcher: read manifest → start services → proxy → cloudflared tunnel |
| `tools/tunnel_auth.py` | Basic Auth reverse proxy with multi-mount path routing (auth before forwarding) |
| `tools/host_metrics.py` | Host metrics collection (CPU / memory / VRAM / GPU) |

```powershell
python -X utf8 tools/start_public_gui.py --single-domain   # one domain + paths
python -X utf8 tools/start_public_gui.py                   # two independent random domains
python -X utf8 tools/start_public_gui.py --status / --stop
```

## Control checks

| Check | Count | Bug it catches |
| :--- | ---: | :--- |
| `tools/check_tunnel_auth.py` | 35 | Auth bypass, prefix not stripped, wrong upstream, unknown prefix 200-fallback |
| `tools/check_tunnel_domain.py` | 10 | Reusing the **previous** domain from append-only logs (530 publicly, fine locally) |
| `tools/check_host_metrics.py` | 23 | Missing readings rendered as 0 (remote thinks the machine is idle) |
| `tools/check_host_metrics_pages.py` | 23 | Pages not wired to the status bar / host page contract broken |
| `tools/check_plugin.py` | 26 | Plugin exports contract, "running" reported while the service is dead |

**A missing dependency must "skip and return 2", never silently pass** — that is the house rule.

## Security boundaries (be honest about them)

- The password is stored **plain text** in `runs/public_gui_credentials.json` and shown plain text
  on the settings page.
- **Whoever has the password can start/stop the exposed service from the internet.**
- Some local services have **no auth of their own** (the two GUIs, Ollama, …); exposing them makes
  them public — the portal password is their only gate.
- This plugin never touches dsh-pocket's own tunnel (target 3081); `--stop` only stops processes
  this repo recorded.

## Tests

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 18 host-side control checks
& $node --test test/client.test.mjs    # 14 client distribution contract checks
```

## Relationship with sibling plugins

`dsh-service-portal` is part of the LaoDing plugin family (same brand icon as
`dsh-connect-workbuddy` / `dsh-connect-trae`). Family members share:

- the settings-card look and `row.*` copy-key conventions;
- handwritten CommonJS client distribution (`window.__ModuleLoader__.load`) with zero build deps;
- the "launcher, not a second implementation" rule: verified tunnel/auth implementations are reused,
  not rewritten inside plugins.

> Historically the portal feature lived in a dedicated child plugin `dsh-poker-viewer`
> (the ld-rl-poker external access switch); on 2026-10-15 its functionality was **absorbed
> into the root plugin** as a generic, manifest-driven portal (not bound to any specific
> service), and the child plugin directory was removed.

## Not done yet

- **Fixed custom domain**: needs a named tunnel + ingress. Today every start gets a random
  trycloudflare domain.
- **Hot-reloadable mount table**: changing the manifest requires restarting the launcher (new domain).
- **Interactive portal page**: the root path is a static list, not a clickable control panel.

## License

MIT, Copyright (c) 2026 LaoDing. Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).