"""Phase C Pass 2: real DockerSandboxExecutor acceptance walkthrough.

Run inside `infra-sandbox-runner-1` (as root, so the docker socket is
accessible). The orchestrator in apps/api always uses the mock; this
script exercises the executor end-to-end against the running Docker
daemon to validate every guarantee called out in
docs/SANDBOX_EXECUTOR.md sections 1-7 of the manual checklist.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import docker
from aidev_shared import TaskPhase

from sandbox_runner.config import SandboxConfig
from sandbox_runner.docker_executor import DockerSandboxExecutor


def banner(text: str) -> None:
    print()
    print("==================== " + text + " ====================")


def jdump(label: str, obj: object) -> None:
    print(label + ":", json.dumps(obj, indent=2, default=str))


def curl_from_host(client: docker.DockerClient, url: str, timeout: int = 5) -> str:
    """Curl `url` from a one-shot `--network host` sidecar so that
    127.0.0.1 means the *VPS host's* loopback (not the sandbox-runner's).
    Returns the HTTP status code as a string, or '000' on failure.
    """

    try:
        out = client.containers.run(
            image="alpine:latest",
            command=[
                "sh",
                "-lc",
                "apk add --no-cache curl >/dev/null 2>&1 || true; "
                f"curl -sS -o /dev/null --max-time {timeout} "
                f"-w '%{{http_code}}' '{url}' || echo '000'",
            ],
            network_mode="host",
            remove=True,
            stdout=True,
            stderr=False,
        )
        text = out.decode("utf-8", errors="replace").strip()
        return (text.splitlines() or ["000"])[-1].strip() or "000"
    except Exception as exc:
        return f"000(exc:{exc!r})"


async def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        prefix = "PASS" if ok else "FAIL"
        line = f"  [{prefix}] {name}"
        if detail:
            line += f"  -- {detail}"
        print(line)
        if not ok:
            failures.append(name)

    cfg = SandboxConfig.from_env()
    banner("0. config (from /opt/aidev/infra/.env)")
    jdump("cfg", {
        "image": cfg.image,
        "cpus": cfg.cpus,
        "mem_limit": cfg.mem_limit,
        "pids_limit": cfg.pids_limit,
        "read_only_root": cfg.read_only_root,
        "agent_uid": cfg.agent_uid,
        "preview_mode": cfg.preview_mode,
        "preview_public_host": cfg.preview_public_host,
        "preview_port_range_start": cfg.preview_port_range_start,
        "preview_port_range_end": cfg.preview_port_range_end,
        "egress_proxy_url": cfg.egress_proxy_url,
        "egress_proxy_alias": cfg.egress_proxy_alias,
        "model_server_host": cfg.model_server_host,
        "task_timeout_seconds": cfg.task_timeout_seconds,
    })

    client = docker.from_env()
    # Pre-pull the curl sidecar image so the first curl_from_host() call
    # doesn't time out fetching it from the registry mid-test.
    try:
        client.images.get("alpine:latest")
    except docker.errors.ImageNotFound:
        print("  prefetching alpine:latest for host-curl sidecar ...")
        client.images.pull("alpine", tag="latest")

    executor = DockerSandboxExecutor(config=cfg, docker_client=client)
    task_id = f"acceptance-{int(time.time())}"
    network_name = cfg.network_name(task_id)
    volume_name = cfg.volume_name(task_id)
    container_name = cfg.container_name(task_id)

    print(f"  task_id={task_id}")
    print(f"  container_name={container_name}")
    print(f"  network_name={network_name}")
    print(f"  volume_name={volume_name}")

    banner("1. container safety profile (kernel-level)")
    saved_port = None
    async with executor.session(
        task_id=task_id, initial_phase=TaskPhase.FRONTEND_CODING
    ) as session:
        c = session.container
        c.reload()
        host_cfg = c.attrs["HostConfig"]
        cfg_section = c.attrs["Config"]

        check(
            "mem_limit == 4g",
            host_cfg.get("Memory") == 4 * 1024**3,
            f"got {host_cfg.get('Memory')}",
        )
        check(
            "nano_cpus == 2.0",
            host_cfg.get("NanoCpus") == 2_000_000_000,
            f"got {host_cfg.get('NanoCpus')}",
        )
        check(
            "pids_limit == 512",
            host_cfg.get("PidsLimit") == 512,
            f"got {host_cfg.get('PidsLimit')}",
        )
        check(
            "read_only rootfs",
            host_cfg.get("ReadonlyRootfs") is True,
            f"got {host_cfg.get('ReadonlyRootfs')}",
        )
        check(
            "no-new-privileges",
            "no-new-privileges:true" in (host_cfg.get("SecurityOpt") or []),
            f"got {host_cfg.get('SecurityOpt')}",
        )
        check(
            "cap_drop == ALL",
            host_cfg.get("CapDrop") == ["ALL"],
            f"got {host_cfg.get('CapDrop')}",
        )
        check(
            "cap_add minimal (CHOWN, FOWNER only)",
            set(host_cfg.get("CapAdd") or []) == {"CHOWN", "FOWNER"},
            f"got {host_cfg.get('CapAdd')}",
        )
        check(
            "user == 10001:10001",
            cfg_section.get("User") == "10001:10001",
            f"got {cfg_section.get('User')}",
        )
        check(
            "network is per-task",
            host_cfg.get("NetworkMode") == network_name,
            f"got {host_cfg.get('NetworkMode')}",
        )

        net = client.networks.get(network_name)
        net.reload()
        # Sandbox network is a plain bridge (NOT internal=true). See
        # _create_network's design note: internal=true breaks published
        # ports and enable_ip_masquerade=false hijacks the proxy's
        # default gateway. The cooperative HTTP_PROXY egress model is
        # the documented trade-off.
        check(
            "network is a plain bridge (port-publish works)",
            net.attrs.get("Internal") is False
            and net.attrs.get("Driver") == "bridge",
            f"internal={net.attrs.get('Internal')} "
            f"driver={net.attrs.get('Driver')}",
        )

        ports = host_cfg.get("PortBindings") or {}
        published = ports.get("3000/tcp")
        if published:
            try:
                saved_port = int(published[0]["HostPort"])
            except Exception:
                saved_port = None
        check(
            "preview port published 3000/tcp -> host port",
            saved_port is not None and 31000 <= saved_port <= 31999,
            f"got {published}",
        )

        mounts = host_cfg.get("Binds") or []
        check(
            "no docker socket bind",
            all("docker.sock" not in (m or "") for m in mounts),
            f"binds={mounts}",
        )

        banner("2. fs protection blocks backend pre-approval (kernel-level)")
        # /workspace is owned by the agent UID; only the owner can create
        # new entries because root inside the sandbox does NOT have
        # CAP_DAC_OVERRIDE (we only re-added CHOWN+FOWNER, see
        # docker_executor._create_container).
        scaffold = await session.run(
            "mkdir -p apps/api apps/web infra && "
            "touch apps/api/main.py apps/web/page.tsx infra/docker-compose.yml .env",
            user=10001,
        )
        check(
            "scaffold mkdir+touch (as agent uid)",
            scaffold.returncode == 0,
            f"rc={scaffold.returncode} stderr={scaffold.stderr.strip()[:160]}",
        )

        # Re-assert phase so the fs-protection script runs against the
        # files we just created.
        await session.set_phase(TaskPhase.FRONTEND_CODING)

        backend_blocked = await session.run(
            "echo x > apps/api/main.py", user=10001
        )
        check(
            "backend write blocked during FRONTEND_CODING",
            backend_blocked.returncode != 0,
            f"rc={backend_blocked.returncode} "
            f"stderr={backend_blocked.stderr.strip()[:120]}",
        )

        infra_blocked = await session.run(
            "echo x > infra/docker-compose.yml", user=10001
        )
        check(
            "infra write blocked during FRONTEND_CODING",
            infra_blocked.returncode != 0,
            f"rc={infra_blocked.returncode} "
            f"stderr={infra_blocked.stderr.strip()[:120]}",
        )

        env_blocked = await session.run("echo x > .env", user=10001)
        check(
            ".env write blocked during FRONTEND_CODING",
            env_blocked.returncode != 0,
            f"rc={env_blocked.returncode} "
            f"stderr={env_blocked.stderr.strip()[:120]}",
        )

        frontend_ok = await session.run(
            "echo hi > apps/web/page.tsx", user=10001
        )
        check(
            "frontend write allowed during FRONTEND_CODING",
            frontend_ok.returncode == 0,
            f"rc={frontend_ok.returncode} "
            f"stderr={frontend_ok.stderr.strip()[:120]}",
        )

        banner("3. BACKEND_UNLOCKED unlocks backend but keeps .env locked")
        await session.set_phase(TaskPhase.BACKEND_UNLOCKED)
        backend_ok = await session.run(
            "echo x > apps/api/main.py", user=10001
        )
        check(
            "backend write allowed during BACKEND_UNLOCKED",
            backend_ok.returncode == 0,
            f"rc={backend_ok.returncode} "
            f"stderr={backend_ok.stderr.strip()[:120]}",
        )
        env_still = await session.run("echo x > .env", user=10001)
        check(
            ".env STAYS locked during BACKEND_UNLOCKED",
            env_still.returncode != 0,
            f"rc={env_still.returncode} stderr={env_still.stderr.strip()[:120]}",
        )

        banner("4. egress allowlist via tinyproxy sidecar")
        proxy_env = await session.run(
            "env | grep -E '^(HTTP|HTTPS|NO)_PROXY' || true"
        )
        print("  proxy env:", proxy_env.stdout.strip())

        gh = await session.run(
            "curl -sS -o /dev/null --max-time 15 -w '%{http_code}' "
            "https://api.github.com/zen"
        )
        check(
            "egress allowed: api.github.com -> 2xx",
            gh.stdout.strip().startswith(("200", "201", "204")),
            f"http={gh.stdout.strip()} rc={gh.returncode}",
        )

        bad = await session.run(
            "curl -sS -o /dev/null --max-time 10 -w '%{http_code}' "
            "https://attacker.test"
        )
        denied_codes = {"403", "502", "504", "000"}
        check(
            "egress denied: attacker.test (4xx/5xx/000)",
            bad.stdout.strip() in denied_codes,
            f"http={bad.stdout.strip()} rc={bad.returncode}",
        )

        anchor = await session.run(
            "curl -sS -o /dev/null --max-time 10 -w '%{http_code}' "
            "https://github.com.attacker.test"
        )
        check(
            "egress regex anchored: github.com.attacker.test denied",
            anchor.stdout.strip() in denied_codes,
            f"http={anchor.stdout.strip()} rc={anchor.returncode}",
        )

        bypass = await session.run(
            "unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; "
            "curl -sS --connect-timeout 5 -o /dev/null "
            "-w '%{http_code}' https://1.1.1.1"
        )
        # Informational: the kernel-level outbound block is NOT enabled
        # in this build (see _create_network design note). Egress is
        # gated by HTTP_PROXY env vars + tinyproxy. We log what the
        # bypass attempt does so the acceptance report can record the
        # state, but we do not fail the run on it.
        print(
            "  [INFO] direct bypass attempt (1.1.1.1 without HTTP_PROXY): "
            f"http={bypass.stdout.strip()!r} rc={bypass.returncode} "
            "-- cooperative-egress model, kernel block deferred to v0.2"
        )

        banner("5. preview registration (port mode)")
        # `exec_run(detach=True)` does NOT wait for the command to exit
        # and does NOT kill the child when the RPC returns.
        c.exec_run(
            cmd=[
                "sh",
                "-c",
                "exec python3 -u -m http.server 3000 --bind 0.0.0.0 "
                "</dev/null >/tmp/srv.log 2>&1",
            ],
            user="10001",
            workdir=cfg.workspace_path,
            detach=True,
        )
        if session.port_allocation is not None:
            session.preview_url = session.port_allocation.public_url
            print("  preview_url:", session.preview_url)
            host_port = session.port_allocation.host_port
            check(
                "port_allocation matches host published port",
                host_port == saved_port,
                f"alloc={host_port} container_pub={saved_port}",
            )
            # First wait for the in-container server to bind.
            for _ in range(20):
                r = c.exec_run(
                    [
                        "sh",
                        "-c",
                        "curl -sS --max-time 2 -o /dev/null "
                        "-w '%{http_code}' http://127.0.0.1:3000/ || true",
                    ],
                    user="10001",
                )
                code = (r.output or b"").decode(errors="replace").strip()
                if code == "200":
                    break
                time.sleep(0.5)
            check(
                "agent server bound 3000 inside container (in-container curl)",
                code == "200",
                f"http={code!r}",
            )

            # Then verify the host-side port mapping: curl from a sidecar
            # with network_mode=host so 127.0.0.1 means *the VPS host*.
            host_code = curl_from_host(
                client, f"http://127.0.0.1:{host_port}/", timeout=5
            )
            check(
                "host curl 127.0.0.1:<host_port>/ returns 200",
                host_code == "200",
                f"http={host_code!r}",
            )

            # And the public preview URL (operator side):
            pub_code = curl_from_host(
                client, session.preview_url, timeout=5
            )
            check(
                "operator curl <public-host>:<host_port>/ returns 200",
                pub_code == "200",
                f"http={pub_code!r}",
            )
        else:
            check("port_allocation set", False, "session.port_allocation is None")

    banner("6. cleanup on exit (DONE happy path)")
    try:
        client.containers.get(container_name)
        check("container removed", False, "container still exists")
    except docker.errors.NotFound:
        check("container removed", True)

    try:
        client.volumes.get(volume_name)
        check("volume removed", False, "volume still exists")
    except docker.errors.NotFound:
        check("volume removed", True)

    try:
        client.networks.get(network_name)
        check("network removed", False, "network still exists")
    except docker.errors.NotFound:
        check("network removed", True)

    released = curl_from_host(client, f"http://127.0.0.1:{saved_port}/", timeout=3)
    check(
        "host port released after teardown (curl from host net)",
        released != "200",
        f"http={released!r}",
    )

    banner("7. cleanup on exception (mid-run failure path)")
    task_id2 = f"acceptance-fail-{int(time.time())}"
    network_name2 = cfg.network_name(task_id2)
    volume_name2 = cfg.volume_name(task_id2)
    container_name2 = cfg.container_name(task_id2)

    class BoomError(RuntimeError):
        pass

    try:
        async with executor.session(task_id=task_id2) as session:
            print(f"  inside session task_id={task_id2}")
            raise BoomError("simulated agent crash")
    except BoomError:
        print("  caught BoomError (expected)")

    try:
        client.containers.get(container_name2)
        check("container cleaned after exception", False)
    except docker.errors.NotFound:
        check("container cleaned after exception", True)
    try:
        client.volumes.get(volume_name2)
        check("volume cleaned after exception", False)
    except docker.errors.NotFound:
        check("volume cleaned after exception", True)
    try:
        client.networks.get(network_name2)
        check("network cleaned after exception", False)
    except docker.errors.NotFound:
        check("network cleaned after exception", True)

    banner("8. port slot recycled on next allocation")
    task_id3 = f"acceptance-recycle-{int(time.time())}"
    async with executor.session(task_id=task_id3) as session:
        rec_port = (
            session.port_allocation.host_port if session.port_allocation else None
        )
        print(f"  task_id3 allocated port={rec_port}")
        check(
            "port recycled into 31000-31999",
            rec_port is not None and 31000 <= rec_port <= 31999,
            f"got {rec_port}",
        )

    banner("=== SUMMARY ===")
    if failures:
        print(f"  FAILURES ({len(failures)}):")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("  ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
