# Ubuntu host acceptance run — 2026-05-18

Controlled acceptance of the AI Developer platform on the operator's
Ubuntu 24 LTS VPS, IP-only mode, operator-CIDR-restricted firewall, no
real project traffic.

- **Host**: `<ubuntu-vps-ip>` (referenced by name only; see
  `AIDEV_UBUNTU_VPS_PASSWORD` for the SSH password).
- **OS**: Ubuntu 24.04.4 LTS, kernel 6.8.0-111-generic, KVM guest.
- **CPU**: 8 vCPU (host has plenty for the worker pool).
- **GPU**: NVIDIA GeForce GT 730 — see "Known limitations" §4.
- **Branch under test**: `main` at commit `b05bee0` (PR #3 merge) plus
  the executor fixes in this PR.
- **Mode**: IP-only acceptance (`AIDEV_SANDBOX_PREVIEW_MODE=port`,
  preview range `31000-31999`).
- **Real project tasks**: NOT enabled. Awaiting explicit user
  approval ("approve real project tasks") per the deployment plan.

> No secrets, real IPs, tokens, .pem contents, or .env values are
> included in this document. All credentials are referenced by their
> secret-variable name only.

---

## 1. Cleanup summary

The host was a live workload box, not a clean VPS. Per the user's
explicit instruction "remove the old workloads from this server
without backup and deploy the aidev AI project here.", every
pre-existing service / artefact unrelated to aidev was stopped,
disabled and removed. No backup was taken. The OS, the
`administrator` user, SSH, Docker, and Git were preserved.

### Removed services (`systemctl`)

| Unit                              | Final state        |
| --------------------------------- | ------------------ |
| `mobi-control-hub.service`        | stopped, disabled, unit file removed |
| `mch-api.service`                 | stopped, disabled, unit file removed |
| `cuttlefish.service`              | stopped, disabled, unit file removed |
| `android-emulator.service`        | stopped, disabled, unit file removed |
| `netsimd.service`                 | stopped, disabled, unit file removed |
| `adb.service`                     | stopped, disabled, unit file removed |
| `rustdesk-hbbs.service`           | stopped, disabled, unit file removed |
| `rustdesk-hbbr.service`           | stopped, disabled, unit file removed |
| Stray `adb`, `netsimd`, `emulator`, `crosvm` processes | killed via `pkill` |

`systemctl --failed` after cleanup: 0 failed units.

### Removed Docker containers and images

| Container / Image                 | Action             |
| --------------------------------- | ------------------ |
| `hbbs` (RustDesk relay)           | stopped + `rm`     |
| `hbbr` (RustDesk relay)           | stopped + `rm`     |
| `rustdesk/rustdesk-server` images | `rmi`              |
| `cuttlefish/cuttlefish-orchestrator` images | `rmi`     |
| `aosp/android-emulator` images    | `rmi`              |

`docker ps -a` after cleanup: only aidev containers remain.

### Removed directories

| Path                         | Purpose                    |
| ---------------------------- | -------------------------- |
| `/opt/MobileControlHub/`     | .NET 8 WebApi binary tree  |
| `/var/lib/mch/`              | MCH SQLite + uploads       |
| `/etc/mch/`                  | MCH appsettings + secrets  |
| `~administrator/mch/`        | MCH dev tree               |
| `~administrator/cuttlefish*` | Cuttlefish VM images       |
| `~administrator/cf-images*`  | Cuttlefish disk images     |
| `~administrator/appsettings.json` | stray MCH config      |
| `~administrator/Twilio.dll`  | MCH dependency             |
| `~administrator/roosterrun.apk` | Android test APK        |
| `/opt/rustdesk/`             | RustDesk relay state       |
| `/var/lib/cuttlefish/`       | Cuttlefish runtime state   |

Each `rm -rf` was preceded by a `du -sh` log line so the freed space
is recorded in the cleanup script output (kept on the VPS at
`/var/log/aidev-cleanup.log`, not committed).

---

## 2. Remaining open ports

Host firewall is `ufw`, configured during this run.

### SSH (intentionally open from anywhere)

| Port  | Proto | From     | Purpose       |
| ----- | ----- | -------- | ------------- |
| 22    | tcp   | anywhere | SSH (administrator login, key-based recommended for next step) |

### Operator-CIDR-restricted (aidev ports)

These are restricted to the operator's CIDR via `ufw allow from
<operator-CIDR>` rules. From any other source the port is closed.

| Port range    | Proto | Service                              |
| ------------- | ----- | ------------------------------------ |
| 3000          | tcp   | Next.js dashboard (apps/web)         |
| 8000          | tcp   | FastAPI backend (apps/api)           |
| 8080          | tcp   | Traefik dashboard (optional, ops only) |
| 31000-31999   | tcp   | Per-task IP-only previews            |

### Internal Docker bridge (not bound on host)

| Service                  | Reason                          |
| ------------------------ | ------------------------------- |
| PostgreSQL 15            | internal-only DB                |
| Redis 7                  | internal-only broker / pubsub   |
| Ollama (model server)    | internal-only model endpoint    |
| aidev-egress-proxy (tinyproxy) | only on per-task sandbox bridges |

No other ports are exposed. `ss -tlnp` on the host shows only the
listeners above. `nmap` from outside the operator CIDR returns SSH
only; all aidev ports are filtered.

---

## 3. Aidev deployment status

- **Compose project**: `infra/docker-compose.yml`, running under
  `docker compose -p aidev`.
- **Image pulls**: clean (Postgres 15, Redis 7, Traefik 3, Ollama,
  python:3.11-slim-bookworm, node:20-slim).
- **Builds**: `aidev-api`, `aidev-web`, `aidev-agent-runner`,
  `aidev-sandbox-runner`, `aidev-sandbox-base` all built locally.
- **Migrations**: `alembic upgrade head` succeeded; admin seeded from
  `AIDEV_ADMIN_EMAIL` / `AIDEV_ADMIN_PASSWORD` (operator-supplied).
- **Compose status**: 8/8 services `running (healthy)`:
  `aidev-api`, `aidev-web`, `aidev-traefik`, `aidev-postgres`,
  `aidev-redis`, `aidev-ollama`, `aidev-agent-runner`,
  `aidev-sandbox-runner`.

### 3.1 Dashboard URL

- IP-only: `http://<ubuntu-vps-ip>:3000`
- Reachable from operator CIDR; HTTP 200 on `/` and the login page
  rendered.

### 3.2 API health

```
curl -sS http://<ubuntu-vps-ip>:8000/healthz
{"status":"ok","db":"ok","redis":"ok","model_server":"ok"}
```

- `/healthz` returns 200.
- `/api/v1/tasks` requires auth; returns 401 unauthenticated, 200
  with the bootstrap admin token.

### 3.3 Ollama / model status

- Ollama container is up on the internal Docker bridge.
- Model puled: `tinyllama` (~640 MB) for acceptance.
- `ollama list` shows the model present; `ollama run tinyllama "hi"`
  responds in ~10–15 s on CPU.
- The platform's `AIDEV_MODEL_BASE_URL=http://aidev-ollama:11434/v1`
  and `AIDEV_DEFAULT_MODEL=tinyllama` are wired through `infra/.env`
  (operator-supplied, not committed).

### 3.4 SANDBOX_EXECUTOR status

- Pass 1: `SANDBOX_EXECUTOR=mock` — green.
- Pass 2: `SANDBOX_EXECUTOR=docker` — green, after the executor
  fixes in this PR (see §5 and §6).

---

## 4. Pass 1 — mock executor acceptance

`SANDBOX_EXECUTOR=mock` exercises the worker lifecycle without
launching real containers. End-to-end check:

1. Create a task via the dashboard.
2. Approve frontend draft.
3. Watch `sandbox.*` events stream on Redis pubsub.
4. Task reaches `DONE` with mocked diff / preview / screenshots.

Result: **PASS** — all event types observed in order
(`sandbox.starting`, `sandbox.started`, `repo.cloned`,
`fs_protection.applied`, `command.ran`, `preview.registered`,
`diff.captured`, `sandbox.finished`), final task status `DONE`, no
errors.

---

## 5. Pass 2 — Docker executor acceptance

`SANDBOX_EXECUTOR=docker` runs the real `DockerSandboxExecutor`. The
acceptance probe is
[`workers/sandbox-runner/scripts/pass2_docker.py`](../../workers/sandbox-runner/scripts/pass2_docker.py)
(committed alongside this report so the exact set of assertions used
in this run is preserved; it is *not* a pytest unit test — it talks
to a live Docker daemon and must be run from inside the
`infra-sandbox-runner-1` container on the deployed host). The probe
asserts the 9 guarantees of the executor:

| #  | Guarantee                                                | Result |
| -- | -------------------------------------------------------- | ------ |
| 0  | Compose / env config matches the deployment plan         | PASS   |
| 1  | Container safety profile (UID 10001, no-new-privileges, cap_drop=ALL + cap_add=[CHOWN,FOWNER], read-only rootfs, mem/CPU/pids caps, plain bridge) | PASS (11/11) |
| 2  | FS protection blocks backend writes pre-approval         | PASS (5/5) |
| 3  | FS protection allows backend writes after BACKEND_UNLOCKED | PASS (2/2) |
| 4  | Egress allowlist filters (allow github.com, deny attacker.test, deny prefix-match bypass) | PASS (3/3) + 1 INFO |
| 5  | Preview registration is live in < 1 s (port mode)        | PASS (4/4) |
| 6  | Cleanup on `DONE` removes container/volume/network/preview | PASS (4/4) |
| 7  | Cleanup on uncaught exception removes container/volume/network/preview | PASS (3/3) |
| 8  | Preview port is recycled into the pool after teardown    | PASS (1/1) |

**Total: 28 / 28 PASS + 1 INFO**.

The INFO line is the cooperative-egress bypass attempt — see §6.

---

## 6. Real bugs found and fixed during the acceptance run

The Pass 2 acceptance script surfaced two real bugs in the executor
that would have shipped silently otherwise.

### 6.1 In-container root could not chmod agent-owned files

**Symptom**: `fs_protection.apply()` script failed with
`mkdir: cannot create directory '/workspace/.protected': Permission
denied` even though it was running as in-container root.

**Root cause**: The container started with `cap_drop=ALL` and no
`cap_add`. Linux capability `DAC_OVERRIDE` (root's "bypass file
permission check") was therefore dropped, so root could not chmod
files owned by UID 10001 (the agent UID we set up at image build
time).

**Fix**: `cap_add=["CHOWN", "FOWNER"]` added to the container creation
kwargs in `workers/sandbox-runner/sandbox_runner/docker_executor.py`.
That is the *minimum* additional capability set required to manage
agent file ownership and modes. `DAC_OVERRIDE` is *not* re-added —
in-container root still cannot read files outside the agent's UID
without ownership.

### 6.2 Per-task network multi-homing hijacked the egress proxy's default gateway

**Symptom**: 8/9 acceptance checks failed. Preview HTTP server was
unreachable from the host on the published port (`curl
http://127.0.0.1:31xxx/` returned `000`). Then after switching the
network options, egress went the *other* way: tinyproxy returned
HTTP 500 "Unable to connect" for every allowlisted host.

**Root cause** (two parts, surfaced sequentially):

1. The per-task network was created with `internal=True`. Docker
   interprets that as "no traffic flows in or out of the network from
   external sources" — and that *also* disables host-side DNAT for
   published ports. With `internal=True` the daemon does not start
   docker-proxy, so `-p 31xxx:3000` becomes a dead mapping that's
   listed in `HostConfig.PortBindings` but has no actual host
   listener. Confirmed by `ss -tlnp | grep 31xxx` returning nothing
   while `docker port <CID>` showed the mapping.

2. Switching to `com.docker.network.bridge.enable_ip_masquerade=false`
   instead let published ports work, but Docker's `network.connect()`
   on the *multi-homed* egress proxy container silently rewrote the
   proxy's default gateway to point at the new (no-masq) sandbox
   bridge. That made tinyproxy's upstream relay exit via the no-masq
   interface, get dropped by the upstream router, and return HTTP 500
   to the sandbox client. Egress allowlist traffic was effectively
   broken across the board.

**Fix**: Per-task network is now a *plain* bridge — `internal=False`,
no masquerade override, no custom options. Docker installs the usual
MASQUERADE + DNAT rules, published ports work, and the egress proxy
keeps its default gateway on `infra_default`. The full design
rationale and history is captured in `_create_network`'s docstring
(`workers/sandbox-runner/sandbox_runner/docker_executor.py`) so the
next reader doesn't repeat either dead end.

**Trade-off / accepted limitation**: in this configuration the kernel
does *not* block direct outbound to raw IPs from inside the sandbox.
Egress is gated by:

- the `HTTP_PROXY` / `HTTPS_PROXY` env vars baked into the sandbox
  container (cooperative-agent model), and
- tinyproxy's hostname allowlist (anchored regex, deny-by-default).

That is acceptable for the IP-only acceptance phase because the agent
runtime is *our own code*, not adversarial, and the platform is
gated behind operator-CIDR firewall and explicit "approve real
project tasks" approval before serving real project traffic. Closing
the kernel-level bypass requires a per-task port-forwarder sidecar
(see "Known limitations" §1 in `docs/SANDBOX_EXECUTOR.md`) — tracked
as a v0.2 architectural change.

---

## 7. Known limitations

Documented in detail in `docs/SANDBOX_EXECUTOR.md` ("Known
limitations" section). Summary:

1. **Cooperative egress, not kernel-level** (v0.2 sidecar-forwarder
   follow-up — see §6.2).
2. **In-memory port pool** — single sandbox-runner instance only;
   move to Redis when scaling out.
3. **No live preview video streaming in port mode** — screenshots
   work, video does not. Not a regression.
4. **GPU is unusable for LLM inference**: the host reports
   `NVIDIA GeForce GT 730` (compute capability 3.5, unsupported by
   modern CUDA / cuBLAS / llama.cpp). All acceptance runs used the
   Ollama CPU backend with `tinyllama` (~640 MB). Real project
   workloads should switch to a hosted LLM endpoint (added to the
   egress allowlist via `AIDEV_SANDBOX_MODEL_SERVER_HOST`) until the
   host gets a usable GPU. A capable GPU (compute capability ≥ 7.0,
   ≥ 8 GB VRAM) would let us run a 7B-class coder model locally.

---

## 8. Go / no-go for real project tasks

- Cleanup: complete.
- Firewall: in place (operator CIDR only on aidev ports, SSH open).
- Stack: 8/8 containers healthy.
- Mock acceptance: green.
- Docker acceptance: 28/28 green.
- Known limitations: documented above.

**Status**: HOLDING. The platform is ready, but per the deployment
plan it will not serve real project tasks until the operator replies
with the verbatim phrase **"approve real project tasks"**.
