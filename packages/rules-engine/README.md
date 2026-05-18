# @aidev/rules-engine

Phase-aware path enforcement for the AI Developer platform.

This package answers a single question:

> Given the current `TaskPhase` and the active rule set, is this agent
> allowed to write to this path?

It is imported by the agent-runner (which gates every write the agent
attempts) and by the FastAPI backend (which surfaces violation reasons
to the dashboard). Keeping it as a separate package means we can
unit-test the policy in isolation.

## Usage

```python
from aidev_rules_engine import Evaluator, RuleViolation
from aidev_shared import TaskPhase

evaluator = Evaluator.from_directory(".ai-rules")

decision = evaluator.evaluate_write(
    path="src/components/Button.tsx",
    phase=TaskPhase.FRONTEND_CODING,
)
if not decision.allowed:
    raise RuleViolation(decision.reason)
```

## Design

- Rules are markdown files with YAML frontmatter under `.ai-rules/`.
- Each rule declares `applies_to: all_phases` or
  `applies_to: phases.FRONTEND_CODING` etc.
- The body contains `allowed_paths` and `forbidden_paths` fenced
  ```glob``` blocks.
- The evaluator merges all active rules and returns a `Decision` with a
  `reason` field — never just a boolean — so the dashboard can show a
  human why the agent's write was blocked.
- `forbidden_paths` always wins over `allowed_paths`. Global
  `forbidden-files.md` always wins over per-project overrides.
