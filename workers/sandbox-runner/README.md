# workers/sandbox-runner

The component that actually executes work inside an isolated sandbox.

In v0.1 only the `MockSandboxExecutor` is implemented — it runs commands
in a temporary directory on the worker host, just enough to drive the
mock task lifecycle. In v0.2 the `DockerSandboxExecutor` replaces it
with the design described in `docs/ARCHITECTURE.md`:

- one ephemeral Docker container per task
- read-only root filesystem
- non-root user
- per-task named volume mounted at `/workspace`
- isolated bridge network with egress whitelist
- resource caps (CPU, memory, PIDs, time)

## Interface

The agent-runner talks to a `SandboxExecutor` via the protocol:

```python
from sandbox_runner import build_executor, SandboxExecutor

executor: SandboxExecutor = build_executor()  # picks Mock or Docker via env

async with executor.session(task_id="...") as sandbox:
    await sandbox.write_file("src/components/Foo.tsx", contents)
    result = await sandbox.run("pnpm build", timeout=600)
    png = await sandbox.read_file(".aidev/screenshots/desktop-1280.png")
```

The session is the unit of cleanup: on exit, the workspace is destroyed.

## Why a separate worker?

Two reasons:
1. The agent-runner is cooperative; the sandbox-runner does dangerous
   work (`docker run`) and benefits from running in a separately
   privileged process with its own resource and security profile.
2. Splitting them lets us scale them independently: one CPU-heavy
   model-bound process per host vs. many sandbox processes (or even
   sandbox VMs).
