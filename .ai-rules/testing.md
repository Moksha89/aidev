---
id: testing
title: Testing requirements
applies_to: all_phases
priority: 70
---

# Testing requirements

Every phase has a different bar; the platform enforces these bars before
moving to the next phase.

## Frontend phase

- Unit tests are optional for purely presentational components.
- Any component with non-trivial state or effects must have a Vitest
  test under `apps/web/tests/`.
- Playwright is the source of truth for visual correctness. The QA
  agent runs:
  - Build (`pnpm build`)
  - Preview (`pnpm start` on a random port)
  - Playwright suite covering the five viewports listed in
    `ui-theme.md`
  - Screenshots saved to `/workspace/.aidev/screenshots/`

## Backend phase

- Every new endpoint must have an integration test under
  `apps/api/tests/` using the FastAPI `TestClient`.
- Every schema change must have a migration that's smoke-tested
  `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
  against a clean DB.
- Coverage of new code: ≥ 70 % lines.

## Security phase

- The Security Reviewer runs `semgrep --config p/owasp-top-ten` against
  the diff (not the whole tree).
- `bandit` is run against any Python file touched.
- `pip-audit` / `npm audit --omit=dev` runs against the lockfile.

## What "failing tests" mean

If any of the above fails:

- Within an agent's own iteration: the agent retries (max 3) and then
  emits a structured `tool_call_error` event.
- Across iterations: the task transitions to `BLOCKED` with the
  reasons, and the dashboard surfaces them to the user.

## What you must not do

- Modify tests to make them pass. Modify the code under test.
- Skip tests with `.skip` / `xfail` to clear the build — surface the
  failure instead.
- Disable lint rules with `// eslint-disable-next-line` or `# noqa`
  unless you can justify it in your final summary.
