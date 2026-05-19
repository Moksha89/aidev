# Rootless Docker — feasibility report

> Scope: should we run the host Docker daemon **rootless** as the
> next sandbox-isolation step beyond v0.3 (docker-socket-proxy)?
>
> Verdict: **not yet — defer to v0.4.** Stay on rootful Docker
> behind the v0.3 socket proxy. See *Recommendation* and *Future
> steps* below for the precise conditions under which we revisit.

---

## 1. What "rootless Docker" actually buys us

`tecnativa/docker-socket-proxy` (v0.3) restricts **which Engine API
endpoints** the worker can call. It does NOT change **who** ultimately
runs those calls: the host's `dockerd` is still `root`, every
container's `runc` is still `root`, and every container UID is mapped
1:1 onto the host UID table by default. A bug in the proxy filter or
a misuse of an *allowed* endpoint (e.g. `POST /containers/create` with
`HostConfig.Privileged=true`) still escalates to host root.

Rootless Docker (`dockerd-rootless-setuptool.sh`, ships with Docker
Engine ≥ 20.10) closes that gap:

* `dockerd` runs as an unprivileged user (e.g. `aidev`).
* Containers run inside that user's user-namespace, so even a
  container "root" maps to a non-zero UID on the host.
* `--privileged` is meaningless (you can't gain caps the daemon
  itself doesn't have).
* A container escape lands you as `aidev`, not as `root` — same
  trust level you'd reach by stealing `aidev`'s SSH key, which we
  already accept.

This is a real defence-in-depth step. But it is also a host-level
re-install of Docker, and it changes the runtime model for *every*
container we ship.

## 2. What it costs us, specifically on this VPS

I walked the v0.2 / v0.3 architecture against the documented rootless
limitations to find concrete blockers. Most of the standard rootless
gotchas do **not** affect us; a small number do.

### 2.1 Non-blockers (we already comply)

| Limitation                                                            | aidev posture                                                                                                              |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Cannot use `--privileged`                                             | We never set it. `cap_drop=ALL` + `cap_add=[CHOWN, FOWNER]` is our floor.                                                   |
| Cannot bind to ports < 1024 by default                                | We bind 3000 (dashboard), 8000 (API), 31000–31999 (per-task preview). All ≥ 1024.                                          |
| Cgroup v2 required for resource caps                                  | Ubuntu 24 LTS is cgroup v2 by default. Our `mem_limit / nano_cpus / pids_limit` all apply.                                 |
| AppArmor profiles must be unconfined or rootless-specific             | We do not ship a custom AppArmor profile; we rely on the default + capability drop.                                        |
| No `overlay` / `macvlan` network drivers                              | We use `bridge` (sandbox internal) and `bridge` (pub) only.                                                                |
| No host-network mode                                                  | Only the acceptance probe's curl sidecar uses `network_mode=host`, and only on the worker side. We can route it via the proxy instead. |
| No raw NFS / iSCSI / SMB volume drivers                               | All workspace volumes are local `bind` / `volume`. No external storage backends.                                           |

### 2.2 Blockers (need a fix before we can flip)

1. **Tecnativa proxy needs to bind the rootless daemon socket.**
   Rootless `dockerd` listens on
   `/run/user/<uid>/docker.sock`, not `/var/run/docker.sock`. The
   compose service currently bind-mounts `/var/run/docker.sock:ro`.
   We'd need:

   * a one-line change in `infra/docker-compose.yml` to bind
     `${XDG_RUNTIME_DIR}/docker.sock`, and
   * the compose project must run **as the `aidev` user**, not as
     root, so XDG_RUNTIME_DIR resolves correctly.

   This second part is the real change — it touches systemd-managed
   `docker.service` and our deploy-time `chown` flow.

2. **Worker UID mapping changes.**
   With rootless, the container's `user: 10001:10001` maps to a
   *subuid* in the host's `/etc/subuid` table (typically
   `100000+10001`). Two effects:

   * Our `/workspace` per-task volumes are created by `dockerd`
     itself in the rootless daemon's data root
     (`/home/aidev/.local/share/docker/volumes/...`). Permissions
     are fine because dockerd owns them, but our backup / inspection
     scripts that assume `/var/lib/docker/volumes/...` need to be
     repathed.
   * Anything we exec on the host as root and then expect the
     container's 10001 to read needs `chown <subuid>:<subgid>`,
     not `chown 10001:10001`. We don't currently rely on this, but
     anyone writing a future repair script must know.

3. **`docker.sock`-replacement permission on container start.**
   Rootless can only `bind` paths inside the daemon-user's
   filesystem namespace. We don't bind the host docker socket into
   the *agent* container anywhere (sanity-checked: see
   `test_session_applies_full_safety_profile`), but the
   docker-socket-proxy *itself* binds `/var/run/docker.sock` — that
   path no longer exists for rootless. Has to become the rootless
   path.

4. **`iptables` MASQUERADE on per-task pub bridges.**
   Rootless Docker uses **slirp4netns** or **rootlesskit** for
   outbound NAT, not host iptables. Two consequences:

   * MTU caps at 65521 (rootlesskit) — fine for HTTP, fine for our
     egress proxy.
   * Outbound source IP is the rootlesskit slirp interface, not the
     host's eth0. This **changes which IP the model server /
     GitHub / npm registry sees as the client**. Operationally
     irrelevant for us (we go through the egress proxy anyway), but
     anyone debugging "why does GitHub see my traffic coming from
     10.0.x.x" will be confused without a heads-up in
     `docs/DEPLOYMENT.md`.

5. **In-tree migration is a re-install, not a config flip.**
   We have to:
   1. Stop the existing `infra` stack.
   2. `apt-get install -y uidmap dbus-user-session`.
   3. Disable the system Docker daemon
      (`systemctl disable --now docker.service docker.socket`).
   4. Create / select the `aidev` user, `loginctl enable-linger aidev`.
   5. As `aidev`: `dockerd-rootless-setuptool.sh install`.
   6. Export `DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock` for
      compose, or run `docker context use rootless`.
   7. `docker compose up -d` from the `aidev` user's home.
   8. Re-run the v0.3 acceptance probe + smoketest before
      re-enabling any task traffic.

   Steps 3 and 5 are not reversible without re-installing Docker, so
   they *must* happen on a clean VPS or in a maintenance window with
   a known-good rollback plan.

### 2.3 Open question: GPU passthrough

Today the VPS has a GeForce GT 730 that we already documented as
unusable for LLM serving (we run Ollama on CPU). If we **ever** add a
real GPU host, rootless Docker + GPU requires either:

* `nvidia-container-runtime` with rootless support (NVIDIA released
  this in container-toolkit 1.13+), **or**
* a dedicated runner host where the daemon stays rootful for the GPU
  case and rootless workers run only on CPU nodes.

Worth knowing now, not actionable now.

## 3. Risk if we flip blindly

The forbidden-action list for this PR explicitly says: "Do not switch
the host to rootless Docker blindly." That guardrail is correct given
this VPS profile:

* **Single-host deploy** — no fallback box. A botched rootless
  reinstall = downtime until the operator re-images.
* **CPU-only Ollama** — model server is running on the same host as
  workers. A reinstall window stops both.
* **Live v0.2 stack** — we already deleted the old MCH / Android /
  Cuttlefish workloads. The aidev stack on this box is the only
  thing of value here; we don't have a second LTS box to fall over
  to during the migration.

If any of step 2.2.5 fails midway (e.g. `subuid` table missing,
`systemd --user` not running for the `aidev` account because that
account was created without `--create-home`), we're stuck with no
Docker on the host and no rollback path that doesn't involve `apt
install docker.io` from scratch.

## 4. Recommendation

**Defer rootless to v0.4.** The blast radius reduction it offers is
real but **incremental** on top of what v0.3 already enforces:

* v0.3 closes "worker → arbitrary host docker run".
* Rootless would close "worker → host root via an allowed docker run
  + a kernel exploit chain", which is already a 2-step compromise
  requiring a working container-escape primitive.

For this VPS, with a single-host deployment that hosts the model
server too, an unattended reinstall is more likely to hand the
operator an outage than to actually thwart the next attacker. Worth
doing — but worth doing on a v0.4 PR with a planned downtime window
and a tested rollback recipe, not as a side effect of the v0.3
hardening pass.

## 5. Future steps (the v0.4 path)

Concrete, in order. Each step is independently revertible.

1. **Stand up a second Ubuntu 24 LTS VPS** as a clean rootless test
   target. Reuse the existing operator `/32` UFW lockdown. Do NOT
   touch the live VPS yet.
2. **Provision rootless Docker** on the test VPS via the official
   `dockerd-rootless-setuptool.sh install` flow. Verify
   `docker info` reports `Security Options: rootless`.
3. **Adapt compose**:
   * Replace `/var/run/docker.sock:ro` on docker-socket-proxy with
     `${XDG_RUNTIME_DIR}/docker.sock:ro`.
   * Add a `user: "${AIDEV_UID}:${AIDEV_GID}"` declaration on the
     proxy service (rootless daemons reject UID-mismatched binds).
   * Add docs note that the compose project must be brought up by
     the unprivileged daemon owner.
4. **Run `pass2_docker.py`** on the test VPS. It will fail the first
   time on the "agent published port reachable from operator IP"
   check because rootless's slirp4netns rewrites the source IP; fix
   the assertion (`pub_code in {"200", ...}` already tolerant).
5. **Run a real-repo smoketest** (one tiny PR-cycle through a
   throwaway repo on the test VPS) with `SANDBOX_EXECUTOR=docker`.
6. **Compare measured blast radius**:
   * Before: kill the agent → root in proxy filter compromise = host
     root.
   * After: same chain = subuid `aidev` only.
7. **Plan a maintenance window** on the live VPS. Communicate the
   downtime in advance. Migrate the live VPS only if all of
   {acceptance probe, smoketest, rollback recipe} are green on the
   test VPS.
8. **Document the rollback**: `dockerd-rootless-setuptool.sh
   uninstall` + reinstall `docker.io` from apt + `docker compose up
   -d` against the existing `infra/docker-compose.yml`. Total
   recovery time on a clean box: under 15 minutes; verify this
   number on the test VPS before scheduling.

Until those steps are checked off on a separate VPS, we stay on
rootful Docker + the v0.3 socket proxy. The v0.3 contract
(`tests/test_docker_executor.py::test_docker_socket_proxy_service_exists_with_hardened_policy`)
remains the security boundary.
