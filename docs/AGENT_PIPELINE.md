# Agent pipeline (v0.4)

This document describes how dashboard tasks travel through the
platform. It documents two parallel paths — `mock` and `real` — and
the single gate that decides which one runs.

> **TL;DR:** the deployed default is `mock`. The `real` path only
> activates when both `AIDEV_AGENT_PIPELINE=real` and
> `SANDBOX_EXECUTOR=docker` are set, and the task is connected to a
> repository row. Anything short of that falls back to the mock
> orchestrator that ships demo data — no Docker, no GitHub, no LLM.

## High level

```
                              ┌───────────────┐
                              │  dashboard    │
                              └──────┬────────┘
                                     │ POST /tasks/:id/start
                                     ▼
                       ┌──────────────────────────┐
                       │  FastAPI route           │
                       └──────────────┬───────────┘
                                      │
                                      ▼
                       ┌──────────────────────────┐
                       │  dispatcher.decide_mode  │
                       └─────┬──────────────┬─────┘
                             │              │
                       mock  │              │  real
                             ▼              ▼
              ┌──────────────────┐   ┌────────────────────┐
              │ in-process       │   │ celery_client      │
              │ orchestrator     │   │ .send_task         │
              │ (demo data)      │   │      │             │
              └──────────────────┘   └──────┼─────────────┘
                                            ▼
                              ┌──────────────────────────┐
                              │ agent-runner (Celery)    │
                              │  pipeline.run_task_async │
                              └──────────┬───────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────┐
                              │ sandbox-runner           │
                              │ DockerSandboxExecutor    │
                              │  (v0.3 socket proxy +    │
                              │   v0.2 sidecar egress)   │
                              └──────────┬───────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────┐
                              │  per-task container      │
                              │  per-task internal net   │
                              │  per-task public net     │
                              │  per-task volume         │
                              │  per-task forwarder      │
                              │  egress-proxy attached   │
                              └──────────────────────────┘
```

## The dispatcher gate

`apps/api/app/services/dispatcher.py` defines a single function,
`decide_mode(task)`, that returns `ExecutionMode.REAL` only if **all
three** conditions are true:

```python
real_mode_active = (
    settings.agent_pipeline == "real"        # AIDEV_AGENT_PIPELINE
    and settings.sandbox_executor == "docker"  # SANDBOX_EXECUTOR
    and task.repository_id is not None         # repo attached
)
```

If any one is false, the dispatcher falls back to the in-process mock
orchestrator (the same path that has been driving the dashboard since
v0.1).

The decision is enforced in two places:

1. **API ingress** — `POST /tasks/:id/start` calls
   `dispatcher.dispatch_start(db, task)`. Mock-mode tasks run
   synchronously inside the FastAPI request and immediately seed demo
   files / preview / logs. Real-mode tasks set
   `task.execution_mode='real'`, transition `phase='planning'`, and
   then `send_task(...)` to the Celery `agent-runner` queue.
2. **Approval path** — `POST /tasks/:id/approve-frontend` reads
   `task.execution_mode` (not the current settings). If the task was
   started in real mode it enqueues
   `agent_runner.tasks.resume_after_approval`; otherwise it runs the
   mock post-approval orchestrator. This stops the operator from
   mid-flight flipping a flag and surprising a half-run task.

The agent-runner re-checks `AgentRunnerConfig.real_pipeline_active`
before doing any work. If a stale Celery message lands on a
mock-configured worker, it logs a warning and returns
`{"phase": "skipped"}` without touching the sandbox.

## Real-mode walkthrough (per task)

1. **Snapshot** — `pipeline._load_task_snapshot` reads the
   `tasks` row + its `repositories` row into a frozen dataclass so
   the rest of the pipeline never holds a DB session while talking to
   Docker / the model server / GitHub.
2. **Branch name** — deterministic
   `aidev/task-<8 hex>-<48-char slug>`; the same name is reused on
   retry so the post-approval push is idempotent.
3. **Planner agent** runs **without** a sandbox. It calls the local
   model via `LLMClient.generate_json`; if the model is unreachable
   or returns garbage it falls back to a deterministic stub plan so
   the pipeline still progresses (and the dashboard sees a real log
   line).
4. **Frontend agent** runs **without** a sandbox. Same fallback
   strategy as the planner. Proposed files are filtered through the
   built-in safe-path filter (`apps/web/**`, `packages/web-*/**`,
   never `.env*`, `apps/api/**`, `workers/**`, etc.) **before** they
   reach the sandbox.
5. **Sandbox opens.**
   `DockerSandboxExecutor().session(task_id, initial_phase=FRONTEND_CODING)`
   creates the per-task container, internal+public networks,
   forwarder sidecar, volume, and attaches the egress proxy. This is
   the v0.2 + v0.3 layout — see
   [`SANDBOX_EXECUTOR.md`](./SANDBOX_EXECUTOR.md).
6. **Clone** — over HTTPS via the egress proxy, with the GitHub PAT
   injected only into the URL's `x-access-token:<PAT>@github.com`
   userinfo. The PAT never appears in logs.
7. **`.ai-rules` load** — if the cloned repo has an `.ai-rules/`
   directory, its YAML files are copied into a tmpdir on the
   agent-runner side, an `Evaluator` is built, and
   `session.set_evaluator(evaluator)` attaches it. From here on,
   every `session.write_file(...)` runs the rules engine; a
   `RuleViolation` is logged as a warn and the write is skipped, the
   pipeline does not crash.
8. **Apply changes** — each proposed file is written, then a sandbox
   commit is made (`git config user.email; git add -A; git commit -m
   'aidev: frontend phase'`).
9. **Best-effort project commands** — `pnpm install`, `pnpm test
   --if-present`, `pnpm build --if-present`. Exit codes are logged
   but never fail the pipeline at v0.4. The smoketest repo is
   intentionally minimal; bigger repos will get a tighter contract
   in v0.5.
10. **Capture** — `session.capture_diff()` (raw `git diff` text) and
    `session.capture_changed_files()`. Both flow into the
    `task_files` table:
    * Rows for paths the frontend agent owns get `content_b64`
      populated (base64-encoded UTF-8 source).
    * Rows for side-effect paths (e.g. `node_modules` install
      artefacts) get `content_b64 = NULL`. The post-approval push
      only commits the former.
11. **Sandbox tears down.** The `async with executor.session(...)`
    block exits and the executor reaps the container, sidecar,
    networks, volume, and forwarder. **The sandbox does not live
    through the approval wait.**
12. **AWAITING_APPROVAL** — the task row is flipped to
    `phase='awaiting_approval'`, `active_agent=None`, and a log line
    is appended. The dashboard polls and shows the diff/preview /
    approval gate.

## Post-approval walkthrough

1. **Resume Celery job** — operator clicks "Approve frontend".
   `dispatch_approve_frontend` sees `execution_mode='real'`,
   transitions `phase='security_review'`, and enqueues
   `agent_runner.tasks.resume_after_approval(task_id)`.
2. **No sandbox is opened.** The post-approval flow only needs the
   staged content + the GitHub client.
3. **Security agent** runs deterministically against the staged
   content. Heuristics flag AWS keys, GitHub PATs, OpenAI keys,
   generic Bearer tokens, `.pem` private-key markers, and
   `password=` literals. A line is whitelisted by adding the
   trailing comment `// noqa: aidev-security` (or `# noqa:
   aidev-security` for Python).
4. **If blocked** — the task moves to `FAILED` with a structured log
   line. No branch push. No PR.
5. **If clean** — `GitHubClient` is built from the configured PAT
   (or, optionally, the GitHub App tuple). The branch is created
   from the base SHA (idempotent — pre-existing branches are
   reused), a single commit is made containing all staged files, and
   a PR is opened. The PR URL + number are stored on the task row;
   the task transitions through `PR_OPENED` → `DONE` and logs the PR
   URL.
6. **Cleanup is automatic.** The sandbox was already torn down at
   step 11 above; the post-approval path never holds Docker
   resources.

## Failure handling

* Both `run_task_async` and `resume_after_approval_async` wrap their
  bodies in `try / except` and call `_fail(task_id, message)` on any
  exception. `_fail` flips the task to `phase='failed'` with an
  `error_message` and appends an `error`-level log line.
* The `DockerSandboxExecutor.session` async context manager runs its
  cleanup in `finally`, so a crash mid-pipeline still tears down
  every container / network / volume / sidecar / forwarder it
  created.
* If the agent-runner crashes hard (SIGKILL, OOM) before reaching the
  `finally` block, the next worker restart's reaper sweeps any
  containers labelled `aidev.task_id=<id>` whose tasks are in a
  terminal state.

## What the dashboard shows

The `<RuntimeBadge />` component (rendered in the topbar) hits
`GET /settings/runtime` once on mount. The response is non-secret
and contains:

```json
{
  "sandbox_executor": "mock" | "docker",
  "agent_pipeline":   "mock" | "real",
  "github_configured": true | false,
  "github_mode":       "token" | "app" | null,
  "real_pipeline_active": true | false,
  "model_base_url":   "http://...:11434/v1",
  "model_name":       "qwen2.5-coder:14b",
  "env":              "development" | "staging" | "production"
}
```

The badge shows `MOCK MODE` or `REAL PIPELINE` depending on
`real_pipeline_active`, with the underlying executor / pipeline /
GitHub-status pills next to it. On individual task cards the
`execution_mode` field surfaces as a `MOCK` or `REAL` tag.

## Configuration matrix

| Flag (env)                   | `mock` (default)             | `real` (opt-in)                              |
| ---------------------------- | ---------------------------- | -------------------------------------------- |
| `AIDEV_AGENT_PIPELINE`       | `mock`                       | `real`                                       |
| `SANDBOX_EXECUTOR`           | `mock`                       | `docker`                                     |
| `AIDEV_GITHUB_TOKEN`         | unset                        | scoped PAT for the smoketest repo only       |
| `AIDEV_MODEL_BASE_URL`       | `http://host…:11434/v1`      | same — Ollama on the host                    |
| `AIDEV_DEFAULT_MODEL`        | `llama3.1:8b-instruct`       | repo-appropriate coder model                 |
| `AIDEV_PR_TITLE_TEMPLATE`    | `aidev: {title}`             | `aidev: {title}`                             |
| `AIDEV_PR_BODY_TEMPLATE`     | default body                 | default body                                 |

You can pre-configure the real flags but leave `AIDEV_GITHUB_TOKEN`
unset; the pre-approval pipeline still runs (it will fail at clone
time if the repo is private, but proves the executor wiring). The
post-approval pipeline refuses to start without GitHub credentials.

## Threat model (delta from v0.3)

The pipeline adds two new trust surfaces compared to the previous
versions:

1. **`agent_runner.pipeline._clone_url`** embeds the GitHub PAT in
   the clone URL. The egress proxy never logs the URL beyond
   `host`+`path`, but a misconfigured logger inside the sandbox
   could leak it. Mitigations: PAT is scoped to a single throwaway
   repo, lives only in env, is never written to disk on the
   agent-runner, and the executor's `safe_print` never echoes it.
2. **GitHub PR write** — the post-approval path can `POST
   /repos/.../pulls` against any repo the PAT can reach. v0.4 ships
   this gated behind both the operator-set flags and the explicit
   `task.repository_id`. Production hardening (GitHub App with
   per-repo installation IDs) is tracked for v0.5; see
   [`GITHUB_INTEGRATION.md`](./GITHUB_INTEGRATION.md).

Everything from v0.3 still applies — the agent has no default route,
the egress proxy is the only outbound path, the Docker socket is
filtered, etc.

## Testing

The dispatcher decision logic is covered by
`apps/api/tests/test_dispatcher.py`. The pipeline safety gate is
covered by `workers/agent-runner/tests/test_pipeline.py`. Agent
fallbacks (no model available) and the rules-engine safe-path filter
have unit tests in `workers/agent-runner/tests/test_agents.py`. The
LLM JSON-extraction helper has tests in
`workers/agent-runner/tests/test_llm.py`. The `/settings/runtime`
endpoint has tests in `apps/api/tests/test_runtime_endpoint.py`.

End-to-end against a real Docker daemon is left to the supervised
smoketest — see `SANDBOX_EXECUTOR.md` §"Manual acceptance checklist".
