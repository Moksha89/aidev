# Sandbox egress sidecar

A tinyproxy container that brokers all HTTP/HTTPS traffic out of the
per-task sandbox containers. The sandbox networks are created with
`internal: true`, so without this sidecar they have **zero** external
connectivity. With it, they can reach the hosts listed in
[`filter`](filter) — and nothing else.

## Why a sidecar?

`docker network create --internal` blocks general egress at the bridge
level. To still allow the sandbox to clone from GitHub or pull packages
from npm / PyPI we need an HTTP(S) proxy on the same internal network.
Tinyproxy fits in <10 MB and supports anchored-regex host filtering
with `FilterDefaultDeny Yes`, which gives us a strict allowlist by
default.

The proxy lives on the host-default bridge **and** on every per-task
`aidev_sandbox_<task_id>` network (attached at run time by the
`DockerSandboxExecutor`). The sandbox receives
`HTTP(S)_PROXY=http://aidev-egress-proxy:8888` in its environment, so
`git`, `pip`, `pnpm`, and `curl` pick it up automatically.

## Updating the allowlist

The source of truth is `sandbox_runner.egress.DEFAULT_ALLOWLIST`. To
regenerate the static filter file after editing the Python list:

```bash
poetry --directory workers/sandbox-runner run python -c \
    'from sandbox_runner.egress import build_allowlist, render_tinyproxy_filter; \
     print(render_tinyproxy_filter(build_allowlist()))' \
  > infra/sandbox/filter
```

Then rebuild the proxy image:

```bash
docker compose -f infra/docker-compose.yml build egress-proxy
docker compose -f infra/docker-compose.yml up -d egress-proxy
```

## Adding a model-server host

Set `AIDEV_SANDBOX_MODEL_SERVER_HOST` in `infra/.env` and either:

1. Re-render the filter with the snippet above (it will pick the env
   var up via `build_allowlist`), or
2. Append the anchored regex manually, e.g.
   `^ollama\.aidev\.local$`.

The model server runs on the host (so it can talk to the GPU
directly), not inside Docker, but the sandbox reaches it through the
egress proxy like any other allowlisted host.

## What's blocked

Anything not in [`filter`](filter): general internet browsing, SSH out,
DNS rebinding, arbitrary IP literals, etc. The `ConnectPort` directives
in `tinyproxy.conf` also restrict the `CONNECT` method to ports 443 /
8443 so the proxy can't be repurposed as a generic TCP tunnel.
