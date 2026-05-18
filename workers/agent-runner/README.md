# workers/agent-runner

The Celery worker that drives a task through its multi-agent lifecycle:

1. **Planner** decomposes the instruction.
2. **Frontend Developer** writes UI code, restricted by the rules engine
   to the frontend-first allowlist.
3. **QA** runs build + Playwright screenshots.
4. *(human approval)*
5. **Backend Developer** writes API + DB code.
6. **Security Reviewer** runs semgrep / bandit.
7. The worker opens the PR.

Every file write is validated against `aidev_rules_engine` before it
touches the workspace. Every model call goes through `aidev_model_client`
and reads the active model server from the database.

## Local run

```bash
cp ../../apps/api/.env.example .env
poetry install
poetry run celery -A agent_runner.worker worker --loglevel=info
```

You'll need the model server (Ollama / vLLM) running and reachable.

## Layout

```
agent_runner/
├── worker.py           # Celery app factory
├── pipeline.py         # the multi-agent state machine
├── agents/
│   ├── base.py         # Agent base class + tool-call protocol
│   ├── planner.py
│   ├── frontend.py
│   ├── backend.py
│   ├── qa.py
│   └── security.py
└── tools/
    ├── workspace.py    # read/write files (rules-engine gated)
    ├── shell.py        # run commands in the sandbox
    └── playwright.py   # screenshot helpers
```

## What's a stub in v0.1

- `agents/*` send a stable, deterministic reply rather than calling the
  model. This lets the dashboard demonstrate the full lifecycle without
  Ollama being up.
- `tools/shell.py` runs commands on the local worker host instead of in
  a Docker sandbox. Replaced by `DockerSandboxExecutor` in v0.2.
- `tools/playwright.py` writes placeholder PNGs instead of running
  Playwright. Replaced by the real call in v0.2.
