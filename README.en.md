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
a **password login** (password only, no username) guards the entrance, and a settings-page toggle
shows the URL and the password.

It originally lived inside `ld-rl-poker` (to put its training dashboard / model viewer online), but the
portal itself has nothing to do with poker — **any local service** can use the same
"one domain + one password + on-demand mount" pattern.

## Features

- **One-click exposure** — the settings page starts the service → auth proxy → tunnel, no manual steps.
- **Password only, no username** — visitors get a custom login page with a single password field;
  the browser's native username+password dialog is never triggered.
- **Two password shapes** — (1) **random per start** (default: smallest leak window);
  (2) a **fixed password you set** (convenient, but once leaked it stays valid — the settings page says so).
- **Random domain** — changes on every start, so the entrance itself is short-lived.
- **Two shapes** — one random domain per service, or **one domain + path prefix**
  (`https://<random>/train/`).
- **Manifest-driven** — write `services.json` to expose any service without touching code; an empty
  manifest falls back to the built-in default (ld-rl-poker's two GUIs, backwards compatible).
- **Control checks** (house rule) — 26 Python control-check scripts plus 8 end-to-end scripts, and 83
  Node checks; **a missing dependency must "skip and return 2", never silently pass**.
- **Host metrics** — CPU / memory / VRAM / GPU utilization; unreadable values render "—", never a fake 0.

## Screenshots

The portal page (what you get after scanning the QR code — read-only: test + guide).
Captured from a real portal process with headless Chrome via `tools/shoot_portal.py`,
not design mockups.

| Phone (light) | Phone (dark) | Wide |
| :---: | :---: | :---: |
| <img src="https://raw.githubusercontent.com/dingminhua/dsh-service-portal/main/docs/assets/portal-phone.png" width="220" alt="portal page, phone, light"> | <img src="https://raw.githubusercontent.com/dingminhua/dsh-service-portal/main/docs/assets/portal-phone-dark.png" width="220" alt="portal page, phone, dark"> | <img src="https://raw.githubusercontent.com/dingminhua/dsh-service-portal/main/docs/assets/portal-wide.png" width="420" alt="portal page, wide"> |

## How it works

```
https://<random>.trycloudflare.com   (cloudflared quick tunnel, new domain every start)
              |
              v
127.0.0.1:<proxyPort>  tools/tunnel_auth.py (password login + session cookie, auth before forwarding)
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

### ⚠ Installing is not enough — enable the bundle too

`dsh plugin add` is a **pnpm wrapper**: it only puts the package into the profile's
`dependencies`. What actually makes the host load a bundle is the profile manifest's
**`dsh.profile.bundles` list** (`~/.dsh/profiles/<profile>/package.json`).
**A package that is only in `dependencies` is never loaded**: the settings page has no
entry for it, every `/service-portal/api/*` call returns 404, and **nothing is logged**.

So after installing, enable the bundle — either way:

- **In the app**: open the Plugins panel, find "DSH Service Portal" and switch it on
  (the in-app plugin manager writes `dsh.profile.bundles` and takes effect immediately,
  no restart needed);
- **By hand**: the CLI cannot do it (`dsh plugin` only forwards to pnpm), so add
  `"dsh-service-portal"` to `dsh.profile.bundles` in
  `~/.dsh/profiles/<profile>/package.json` and restart the host.

> **Check this first after a host upgrade**: a newer host can drop the entry while it
> rewrites the profile manifest. The symptom is "it worked before the upgrade, now the
> plugin page is empty and the API 404s". See "Known limitations" for the diagnosis.

## Configuration (DSH settings page)

| Field | Default | Description |
| :--- | :--- | :--- |
| `infraPath` | this repo root | Infrastructure repo: contains `tools/` and `runs/` (tunnel/proxy/credentials) |
| `repoPath` | **empty** | Host repo root: where the exposed services live. **You must set this** |
| `pythonPath` | empty | Interpreter for services; auto-selects `.venv313` → `.runtime` → PATH |
| `cloudflaredPath` | empty | Path to the `cloudflared` binary; when empty it is auto-detected (`~/.dsh/dsh-pocket/bin` → `~/.dsh/bin` → `~/.local/bin` → `/usr/local/bin` → `/opt/homebrew/bin` → PATH) |
| `passwordMode` | `random` | Password shape: `random` = new password each start / `fixed` = your fixed password |
| `fixedPassword` | empty | Used when `passwordMode = fixed`, at least 12 chars (validated on save) |
| `webEnabled` | `true` | Mount the `/service-portal/api` routes |

All four are `.volatile()`: changes apply immediately without remounting the plugin.

## HTTP API

Mounted on the host webServer (`prefix` routes under `/service-portal/api`):

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/service-portal/api/status` | Current state: running, mode, URL, password, password mode, endpoints |
| GET | `/service-portal/api/settings` | Password-shape settings (mode + fixed password + min length) |
| POST | `/service-portal/api/settings` | Save password shape (`{"passwordMode":"fixed","fixedPassword":"..."}`) |
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
| `tools/tunnel_auth.py` | Password-login reverse proxy with multi-mount path routing (auth before forwarding) |

```powershell
python -X utf8 tools/start_public_gui.py --single-domain   # one domain + paths
python -X utf8 tools/start_public_gui.py                   # two independent random domains
python -X utf8 tools/start_public_gui.py --status / --stop
```

## Control checks

| Check | Count | Bug it catches |
| :--- | ---: | :--- |
| `tools/check_portal_integration.py` | — | A malformed Host counted as LAN (`garbage value` was password-free), double-slash console links |
| `tools/check_portal_registry.py` | 88 | Duplicate/illegal mounts, key collisions, **changes not persisted** (lost on restart), crash on a corrupt file |
| `tools/check_portal_console.py` | — | Disabled services still clickable, `<script>` in a service name (stored XSS), non-deterministic QR |
| `tools/check_portal_proxy.py` | — | **A self-hosted domain judged as LAN**, auth not before forwarding, rate limit not working, forged `cf-connecting-ip` |
| `tools/check_portal_auth.py` | 35 | Unauthenticated access allowed, forged/tampered/expired sessions, password stored in cookie |
| `tools/check_tunnel_auth.py` | 35 | Auth bypass, prefix not stripped, wrong upstream, unknown prefix 200-fallback |
| `tools/check_tunnel_domain.py` | 10 | Reusing the **previous** domain from append-only logs (530 publicly, fine locally) |
| `tools/check_plugin.py` | 41 | Plugin exports contract, "running" reported while the service is dead, bad password mode |

```powershell
python -X utf8 tools\check_portal_integration.py
python -X utf8 tools\check_portal_registry.py
python -X utf8 tools\check_portal_console.py
python -X utf8 tools\check_portal_proxy.py
python -X utf8 tools\check_portal_auth.py
python -X utf8 tools\check_tunnel_auth.py
python -X utf8 tools\check_tunnel_domain.py
python -X utf8 tools\check_plugin.py
```

**A missing dependency must "skip and return 2", never silently pass** — that is the house rule.

## Security boundaries (be honest about them)

- The password is stored **plain text** in `runs/public_gui_credentials.json` and shown plain text
  on the settings page.
- **Sessions are signed cookies** (HttpOnly, 12h by default): that browser stays authorised for
  the window without re-entering the password. The signing key is per-process, so stopping the
  portal logs everyone out.
- **A fixed password keeps working across restarts** — one leak stays valid until you change it.
  Keep the default `random` for temporary sharing.
- Do not expose the portal's own `127.0.0.1` port to the internet: the cloudflared tunnel is the
  only intended way in, and bypassing it bypasses the auth layer entirely.
- **Whoever has the password can start/stop the exposed service from the internet.**
- Some local services have **no auth of their own** (the two GUIs, Ollama, …); exposing them makes
  them public — the portal password is their only gate.
- This plugin never touches dsh-pocket's own tunnel (target 3081); `--stop` only stops processes
  this repo recorded.

## Tests

```powershell
$node = "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
& $node --test test/host.test.mjs      # 55 host-side control checks
& $node --test test/client.test.mjs    # 28 client distribution contract checks

# End-to-end acceptance: launches the real portal process and verifies
# LAN-is-free / public-needs-password / console-manages-services / rate limit / health
python -X utf8 test\acceptance_portal.py    # 30 checks
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

## Marketplace listing

The plugin ships an installable `dsh.bundle` manifest and is published to npm. Community
marketplaces usually sync entries from the
[Awesome DSH Plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) registry; the
in-repo submission draft lives at
[`awesome-dsh-plugin-submission/dingminhua__dsh-service-portal.yml`](https://github.com/dingminhua/dsh-service-portal/blob/main/awesome-dsh-plugin-submission/dingminhua__dsh-service-portal.yml).

> That link is an absolute GitHub URL on purpose: `awesome-dsh-plugin-submission/` and
> `screenshots.json` are **not** in the `files` whitelist of `package.json` (they serve the repo
> and the listing process, not the npm package). A relative link would 404 on the npm page.

**Listing conventions** (per Awesome DSH Plugin's `contributing.md`):

- One YAML per plugin at `data/plugins/<owner>__<repo>.yml` with `url` (must match the repo URL
  exactly), `name` (`owner/repo`), `category` (a valid value; ours is `remote`), and
  `description.en` (required, ends with a period) / `description.zh` (optional). Any description
  containing `: ` must be quoted.
- The repo must declare the `dsh.bundle` manifest (ours: `dsh.bundle.patch: ./cordis.patch.yml`)
  and carry the `dsh-plugin` topic; CI checks for at least 10 commits and a repo age of 1 day.
- At most 3 plugins per PR; only touch your own entry.

Marketplace cards and README badges are two separate mechanisms:

- **GitHub badges** come from the Shields links at the top of this README.
- **Marketplace screenshots** are declared by the plugin's own
  [`screenshots.json`](https://github.com/dingminhua/dsh-service-portal/blob/main/screenshots.json)
  at the repo root; the registry's `data/screenshots.json` is a legacy fallback and takes no new keys.
- **Marketplace icon/placeholder** is decided by each marketplace's own rules — it is neither a
  generic `package.json` field nor a README badge.

## Known limitations

- **Random domain, never fixed**: every start gets a one-off `*.trycloudflare.com`; it dies on
  close or restart and may be recycled by someone else as an unrelated site. A **fixed custom
  domain** needs a named tunnel + ingress, which this plugin does not support. The UI therefore
  keeps saying "do not bookmark, scan the current QR code from this page each time".
- **cloudflared must already be installed**: we reuse the local copy and **never auto-download**
  (sibling dsh-pocket downloads from several mirrors). The settings page tells you **up front**
  what is missing and how to install it: `GET /status` carries a `prereqs` report, both start
  buttons are disabled when Python 3 is missing (nothing can start without it), and when only
  cloudflared is missing just "start with public access" is disabled — "start (LAN only)" still works.
- **Liveness is only probed on refresh**: the console and settings page probe the upstream port
  when opened; there is no background timer, so a service that just died may still look alive
  until you refresh.
- **Public reachability depends on the quick tunnel and Cloudflare edge**: DNS propagation can
  take seconds to tens of seconds; `check_portal_tunnel.py` waits for it before judging. When it
  fails, read the cloudflared log before blaming the plugin.
- **Password-free LAN access is a default, not a security recommendation**: any device on the same
  WiFi can open the portal without a password. On untrusted networks, turn on the LAN password.
  This is a deliberate trade-off (scan-and-go convenience) and the UI states it plainly.
- **Node >= 24 and host API version**: the plugin needs DSH's `webServer` / `settings` capabilities.
  When a host lacks them the plugin fails closed (mounts no routes) instead of half-working.
- **The host silently skips the plugin after an upgrade**: the host only loads bundles listed in
  the profile manifest's `dsh.profile.bundles`. If a newer host rewrites that manifest without
  this entry, the plugin **disappears entirely and logs nothing** — no settings entry, and
  `/service-portal/api/status` returns 404. Diagnosis: if `curl http://127.0.0.1:<port>/service-portal/api/status`
  cannot connect, the plugin is not loaded (that is different from "the portal is not started").
  Fix: switch "DSH Service Portal" back on in the Plugins panel, or write
  `"dsh-service-portal"` back into `dsh.profile.bundles` of
  `~/.dsh/profiles/<profile>/package.json` and restart the host.
- **Windows / macOS / Linux are all verified**, but `cloudflared` candidates are derived from the
  platform plus common install locations; if yours is elsewhere, set `cloudflaredPath` in the
  settings page (a path that does not exist is reported as "you typed it wrong", which is a
  different error from "not installed" and must be handled separately).

## Disclaimer

- This project is **for personal learning and research only**. Use it solely to expose local
  services **you own or are authorised to access**; do not use it commercially or beyond a
  reasonable personal scope.
- **Exposing something publicly is your own decision and your own risk.** Once public access is
  on, anyone holding the address and password can reach your published nodes (they can add, open
  or block nodes, but cannot start or stop the upstream programs). Do not leave an admin password
  exposed publicly for long, and turn public access off when you are done.
- You must comply with Cloudflare's terms of service. Any consequence of using this project
  (including but not limited to domain recycling, tunnel limits, outages, or data exposure) is
  your own responsibility.
- The author accepts no liability for direct or indirect loss arising from the use or misuse of
  this project.
- This project is not affiliated with, nor endorsed by, Cloudflare or DeepSeek. Names appear only
  to describe compatibility; trademarks remain with their respective owners.

## Not done yet

- **Fixed custom domain**: needs a named tunnel + ingress. Today every start gets a random
  trycloudflare domain.
- **Auto-download of cloudflared**: we reuse the local copy (dsh-pocket downloads it from mirrors).
- **Periodic health refresh**: liveness is probed on page refresh, not by a background timer.

## Acknowledgements

This project builds on work others have published. Sources and licences are credited honestly
below:

### The connection kernel reference

The **portal shape** of this project (console web page, internal + external entrances,
authentication strength decided by Host class) explicitly follows
[shaobeichen/dsh-pocket](https://github.com/shaobeichen/dsh-pocket):

> "Put DeepSeek Harness in your pocket: one package, one settings page, scan a QR code on your phone
> to reach the DSH on your computer (LAN + public, live mirror)." — GPL-2.0

**What we learned from it** (each item maps to an implementation here):

| Its approach | Ours |
| :--- | :--- |
| `classifyHost()` splits Host into `loopback` / `lan` / `public` and picks auth strength per class | `tools/portal_proxy.py::classify_host()`, same three classes |
| **fail-closed**: an unrecognised Host counts as public (it was once bypassed by doing the opposite, issue #66) | Same fail-closed rule, plus 20 host-classification checks (including "a self-hosted domain must be public") |
| Public always needs a password; LAN can be toggled; loopback is free | LAN password-free, public password-required (user's choice) |
| Login rate limiting: 5 failures per IP → 60s lock, plus a global threshold | `RateLimiter`, same thresholds |
| `cf-connecting-ip` trusted only when the source is loopback | `client_ip()`, same rule (a forged header cannot bypass the limiter) |
| Custom login page instead of the browser's native auth dialog | `tools/portal_login.py` |
| Scan-and-go on mobile (QR code + mobile layout) | `tools/portal_console.py` (SVG QR generated in pure Python, no new dependency) |

**To be explicit: no code was copied from dsh-pocket.**

- It is JavaScript (`lib/proxy.mjs` / `lib/tunnel.mjs` / `client/`); this project's portal is an
  independent Python implementation (`tools/portal_*.py`) with different structure and naming.
- Their HTTP endpoints, token storage format and config format are all incompatible with ours.
- What we borrowed is **design judgement** (the fail-closed direction, rate-limit thresholds, the IP
  trust boundary — conclusions that cost someone a security incident), implemented from scratch.

So this project's MIT licence is **not** infected by its GPL-2.0: GPL governs distribution of
derivative code, and "learned the design, wrote our own implementation" is not a derivative work.
We credit it and state its licence anyway — out of respect, and so readers can judge for themselves.

> If you ever want to **copy its source** into this project, the whole project would have to move to
> GPL-2.0 — do not mix in its code without that decision.

### Others

- [cloudflared](https://github.com/cloudflare/cloudflared) (Apache-2.0) — the public tunnel.
### The plugin-presentation baseline

- [dingminhua/dsh-connect-workbuddy](https://github.com/dingminhua/dsh-connect-workbuddy)
  (MIT, Copyright (c) 2026 LaoDing) — the plugin presents itself the same way: settings-card
  structure and interactions, the read-only host↔client route shape, the `dsh.bundle` manifest
  and the npm release setup. The **brand icon** (`client/icon.ts`, an inline 64px data URI) is
  **byte-for-byte identical** so the family looks consistent.
- [dingminhua/dsh-connect-trae](https://github.com/dingminhua/dsh-connect-trae) (MIT) and
  [dingminhua/dsh-subagent-default-model](https://github.com/dingminhua/dsh-subagent-default-model)
  (MIT) — origin of the `dsm-*` card style system and the `row.*` bilingual copy keys, via
  `dsh-connect-workbuddy`.

### Other

- [cloudflared](https://github.com/cloudflare/cloudflared) (Apache-2.0) — the public tunnel.
- [mexiaosqwq/dsh-web-mobile](https://github.com/mexiaosqwq/dsh-web-mobile) (MIT) — dsh-pocket's mobile
  adaptation was ported from it; we do not use it directly, but the mobile design originates there.

### Note

Copyright in the projects above belongs to their respective authors. This project takes the
approach of **borrowing design ideas while implementing independently**; no reference project's
source was copied wholesale. Key modules are written from scratch and name the specific project
and pattern they reference in their file headers. If you find an omission or misattribution,
please open an issue and we will correct it immediately.

## Third-party open-source dependencies

The open-source projects this project references, their licences and compliance notes are recorded
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). When adding a new external dependency or
reusing code from another project, update that file and honour the corresponding licence.

## License

MIT, Copyright (c) 2026 LaoDing. Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).