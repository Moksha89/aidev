"""Unit tests for the v0.4 Planner / Frontend / Security agents.

The model server is never contacted: every test either uses ``llm=None``
to exercise the deterministic fallback, or installs a fake
:class:`LLMClient` that returns a hard-coded JSON payload.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_runner.agents.base import FileChange
from agent_runner.agents.frontend import FrontendAgent, _is_safe_path
from agent_runner.agents.planner import PlannerAgent
from agent_runner.agents.security import SecurityReviewerAgent

# --- helpers ---------------------------------------------------------


@dataclass
class _StubLLM:
    """Stub ``LLMClient`` that returns a fixed JSON payload."""

    payload: object

    def generate_json(self, **_kwargs: object) -> object:
        return self.payload


# --- planner --------------------------------------------------------


def test_planner_falls_back_when_llm_is_none() -> None:
    result = PlannerAgent().plan(
        instruction="Add an about page",
        title="About page",
        llm=None,
    )
    assert result.used_model is False
    plan = result.output["plan"]
    assert isinstance(plan, list) and 1 <= len(plan) <= 5
    assert "About page" in (result.chat_message or "")


def test_planner_uses_llm_when_valid_json() -> None:
    fake = _StubLLM(
        payload={
            "plan": [
                {"step": "Add page route", "role": "frontend"},
                {"step": "Wire mock data", "role": "frontend"},
                {"step": "Run tests", "role": "qa"},
            ]
        }
    )
    result = PlannerAgent().plan(
        instruction="x", title="Add Page", llm=fake  # type: ignore[arg-type]
    )
    assert result.used_model is True
    assert [s["step"] for s in result.output["plan"]] == [
        "Add page route",
        "Wire mock data",
        "Run tests",
    ]


def test_planner_drops_backend_steps_before_approval() -> None:
    fake = _StubLLM(
        payload={
            "plan": [
                {"step": "Add page", "role": "frontend"},
                {"step": "Migrate DB", "role": "backend"},
            ]
        }
    )
    result = PlannerAgent().plan(
        instruction="x", title="t", llm=fake  # type: ignore[arg-type]
    )
    roles = [s["role"] for s in result.output["plan"]]
    assert "backend" not in roles


def test_planner_falls_back_on_invalid_payload() -> None:
    fake = _StubLLM(payload={"unexpected": "shape"})
    result = PlannerAgent().plan(
        instruction="x", title="t", llm=fake  # type: ignore[arg-type]
    )
    assert result.used_model is False
    assert result.output["plan"]  # deterministic fallback ran


# --- frontend -------------------------------------------------------


def test_frontend_falls_back_when_llm_is_none() -> None:
    result = FrontendAgent().code(
        instruction="Add an about page",
        title="About page",
        plan=[{"step": "Scaffold", "role": "frontend"}],
        slug="about",
        llm=None,
    )
    assert result.used_model is False
    paths = [c.path for c in result.changes]
    assert "AIDEV_TASK.md" in paths
    assert any(p.startswith("apps/web/app/aidev/") for p in paths)


def test_frontend_uses_llm_with_safe_path() -> None:
    fake = _StubLLM(
        payload={
            "files": [
                {
                    "path": "apps/web/app/aidev/test/page.tsx",
                    "content": "export default function P(){return null}\n",
                }
            ]
        }
    )
    result = FrontendAgent().code(
        instruction="x",
        title="t",
        plan=[],
        slug="t",
        llm=fake,  # type: ignore[arg-type]
    )
    assert result.used_model is True
    assert result.changes[0].path == "apps/web/app/aidev/test/page.tsx"


def test_frontend_filters_forbidden_paths_from_llm() -> None:
    fake = _StubLLM(
        payload={
            "files": [
                {"path": "apps/api/app/main.py", "content": "evil"},
                {"path": "infra/docker-compose.yml", "content": "evil"},
                {"path": "workers/agent-runner/x.py", "content": "evil"},
                {"path": "../escape.tsx", "content": "evil"},
            ]
        }
    )
    result = FrontendAgent().code(
        instruction="x", title="t", plan=[], slug="t", llm=fake  # type: ignore[arg-type]
    )
    # All proposed files were forbidden — fallback must engage.
    assert result.used_model is False
    for c in result.changes:
        assert _is_safe_path(c.path), c.path


def test_safe_path_blocks_backend_and_secrets() -> None:
    assert _is_safe_path("apps/web/src/lib/foo.ts") is True
    assert _is_safe_path("apps/api/app/main.py") is False
    assert _is_safe_path("workers/agent-runner/x.py") is False
    assert _is_safe_path("infra/docker-compose.yml") is False
    assert _is_safe_path("../escape.tsx") is False
    assert _is_safe_path("/etc/passwd") is False


# --- security -------------------------------------------------------


def test_security_passes_on_clean_changes() -> None:
    changes = [
        FileChange(
            path="apps/web/app/p/page.tsx",
            content="export default function P(){return null}\n",
        ),
        FileChange(path="AIDEV_TASK.md", content="# Hello\n"),
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is False
    assert out.output["findings"] == []


def test_security_blocks_on_aws_key() -> None:
    changes = [
        FileChange(
            path="apps/web/src/config.ts",
            content="const key = 'AKIAABCDEFGHIJKLMNOP';\n",
        )
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is True
    findings = out.output["findings"]
    assert any(f["rule"] == "aws_access_key" for f in findings)


def test_security_blocks_on_github_token() -> None:
    changes = [
        FileChange(
            path="apps/web/app/page.tsx",
            content="const t = 'ghp_" + "A" * 40 + "';\n",
        )
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is True


def test_security_blocks_on_private_key_block() -> None:
    changes = [
        FileChange(
            path="apps/web/app/page.tsx",
            content="-----BEGIN RSA PRIVATE KEY-----\nAAAA\n",
        )
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is True


def test_security_suppression_marker_is_respected() -> None:
    changes = [
        FileChange(
            path="apps/web/src/x.ts",
            content="const t = 'ghp_" + "A" * 40 + "'; // noqa: aidev-security\n",
        )
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is False
    assert out.output["findings"] == []


@pytest.mark.parametrize("severity", ["critical", "high"])
def test_security_blocked_only_for_high_and_above(severity: str) -> None:
    # The medium-only "hardcoded_password" rule must not block by itself.
    if severity == "critical":
        content = "key = 'AKIAABCDEFGHIJKLMNOP'\n"
    else:
        content = "Authorization: bearer ABCDEFGHIJKLMNOPQRST12345\n"
    changes = [FileChange(path="apps/web/src/x.ts", content=content)]
    out = SecurityReviewerAgent().review(changes=changes)
    assert out.output["blocked"] is True


def test_security_medium_password_is_advisory_only() -> None:
    changes = [
        FileChange(
            path="apps/web/src/x.ts",
            content="const password = 'hunter22';\n",
        )
    ]
    out = SecurityReviewerAgent().review(changes=changes)
    # Medium severity must not block but must still report.
    assert out.output["blocked"] is False
    assert any(f["rule"] == "hardcoded_password" for f in out.output["findings"])
