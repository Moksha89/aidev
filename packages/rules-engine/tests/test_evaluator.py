"""Unit tests for the rules engine evaluator.

These exercise the policy that is the centrepiece of the platform:
- frontend-only paths are writable in FRONTEND_CODING
- backend paths are blocked until BACKEND_CODING
- globally forbidden files (.env, secrets, .git, .ai-rules) are blocked
  in every phase
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aidev_shared import TaskPhase

from aidev_rules_engine import Evaluator, RuleViolation, parse_rule

REPO_ROOT = Path(__file__).resolve().parents[3]
AI_RULES_DIR = REPO_ROOT / ".ai-rules"


@pytest.fixture(scope="module")
def evaluator() -> Evaluator:
    return Evaluator.from_directory(AI_RULES_DIR)


class TestFrontendCodingPhase:
    """In FRONTEND_CODING the agent may only touch frontend paths."""

    def test_components_are_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "src/components/Button.tsx", TaskPhase.FRONTEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_pages_are_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "app/dashboard/page.tsx", TaskPhase.FRONTEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_styles_are_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "styles/globals.css", TaskPhase.FRONTEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_mock_data_is_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "src/mocks/tasks.ts", TaskPhase.FRONTEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_package_json_is_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "package.json", TaskPhase.FRONTEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_backend_paths_are_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "apps/api/app/routes/projects.py", TaskPhase.FRONTEND_CODING
        )
        assert not decision.allowed
        assert "apps/api" in decision.reason or "forbidden" in decision.reason

    def test_migrations_are_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "migrations/0001_init.py", TaskPhase.FRONTEND_CODING
        )
        assert not decision.allowed

    def test_alembic_versions_are_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "apps/api/alembic/versions/abc_init.py", TaskPhase.FRONTEND_CODING
        )
        assert not decision.allowed

    def test_payment_logic_blocked_anywhere(
        self, evaluator: Evaluator
    ) -> None:
        decision = evaluator.evaluate_write(
            "src/payments/checkout.ts", TaskPhase.FRONTEND_CODING
        )
        assert not decision.allowed, "payment paths must be blocked"

    def test_wallet_logic_blocked_anywhere(
        self, evaluator: Evaluator
    ) -> None:
        decision = evaluator.evaluate_write(
            "lib/wallet/sign.ts", TaskPhase.FRONTEND_CODING
        )
        assert not decision.allowed


class TestBackendCodingPhase:
    """After approval, backend paths become writable."""

    def test_api_routes_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "apps/api/app/routes/tasks.py", TaskPhase.BACKEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_migrations_allowed(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "apps/api/alembic/versions/abc_init.py", TaskPhase.BACKEND_CODING
        )
        assert decision.allowed, decision.reason

    def test_env_still_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "apps/api/.env", TaskPhase.BACKEND_CODING
        )
        assert not decision.allowed

    def test_deploy_workflow_still_blocked(
        self, evaluator: Evaluator
    ) -> None:
        decision = evaluator.evaluate_write(
            ".github/workflows/deploy-prod.yml", TaskPhase.BACKEND_CODING
        )
        assert not decision.allowed


class TestGloballyForbidden:
    """Some files are forbidden in every phase."""

    @pytest.mark.parametrize(
        "phase",
        [
            TaskPhase.PLANNING,
            TaskPhase.FRONTEND_CODING,
            TaskPhase.BACKEND_CODING,
            TaskPhase.SECURITY_REVIEW,
        ],
    )
    def test_env_files_always_blocked(
        self, evaluator: Evaluator, phase: TaskPhase
    ) -> None:
        decision = evaluator.evaluate_write(".env", phase)
        assert not decision.allowed

    @pytest.mark.parametrize(
        "phase",
        [TaskPhase.FRONTEND_CODING, TaskPhase.BACKEND_CODING],
    )
    def test_ai_rules_always_blocked(
        self, evaluator: Evaluator, phase: TaskPhase
    ) -> None:
        decision = evaluator.evaluate_write(
            ".ai-rules/global.md", phase
        )
        assert not decision.allowed

    def test_pem_files_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "infra/ssl/server.pem", TaskPhase.BACKEND_CODING
        )
        assert not decision.allowed

    def test_id_rsa_blocked(self, evaluator: Evaluator) -> None:
        decision = evaluator.evaluate_write(
            "scripts/id_rsa", TaskPhase.BACKEND_CODING
        )
        assert not decision.allowed


class TestAssertWriteAllowed:
    def test_raises_on_violation(self, evaluator: Evaluator) -> None:
        with pytest.raises(RuleViolation) as excinfo:
            evaluator.assert_write_allowed(
                "apps/api/app/main.py", TaskPhase.FRONTEND_CODING
            )
        assert excinfo.value.decision.allowed is False
        assert excinfo.value.decision.matched_rule_id is not None

    def test_passes_when_allowed(self, evaluator: Evaluator) -> None:
        evaluator.assert_write_allowed(
            "src/components/Foo.tsx", TaskPhase.FRONTEND_CODING
        )


class TestParser:
    def test_parses_inline_rule(self) -> None:
        rule = parse_rule(
            """---
id: test
title: Test rule
applies_to: phases.FRONTEND_CODING
priority: 10
---

# Test rule

## Allowed paths

```glob
foo/**
bar/baz.txt
```

## Forbidden paths

```glob
foo/secret.txt
```
""",
            source_path="<inline>",
        )
        assert rule.id == "test"
        assert rule.allowed_paths == ("foo/**", "bar/baz.txt")
        assert rule.forbidden_paths == ("foo/secret.txt",)
        assert rule.target_phase == "FRONTEND_CODING"
