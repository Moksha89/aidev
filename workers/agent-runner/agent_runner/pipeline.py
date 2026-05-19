"""v0.4 real-pipeline orchestrator.

Two public coroutines drive a dashboard task end-to-end:

* :func:`run_task_async` — pre-approval phase. Opens a Docker sandbox
  via :class:`~sandbox_runner.docker_executor.DockerSandboxExecutor`,
  clones the connected repository, runs the Planner + Frontend agents,
  writes their proposed files through the rules engine, captures the
  diff + changed-file list, stages the file content (base64) to the
  ``task_files`` table, and transitions the task to
  :data:`~aidev_shared.TaskPhase.AWAITING_APPROVAL`. The sandbox is
  torn down before the function returns so a long approval window
  doesn't hold Docker resources.

* :func:`resume_after_approval_async` — post-approval phase. Does NOT
  open a sandbox (the staged content is already in the DB). Runs the
  deterministic security review against the staged content; if it
  passes, pushes the branch + opens a real PR via the existing
  :class:`~aidev_github.GitHubClient`. On a clean PR the task moves
  through :data:`PR_OPENED` → :data:`DONE`. If the security gate
  blocks, the task moves to :data:`FAILED` with a structured log
  entry and no PR is opened.

Both coroutines catch every exception at the top level and convert it
to :data:`FAILED` + an ``error_message`` on the task row so the
dashboard always shows a deterministic terminal state.

Secrets contract:

* The GitHub PAT is read from :class:`AgentRunnerConfig` and used only
  in the ``Authorization`` header to ``api.github.com`` and as the
  password component of ``https://x-access-token:<PAT>@github.com/...``
  clone URLs. It must never appear in logs, error messages, PR
  bodies, or screenshots.
* The local-model endpoint URL and model name are non-secret and may
  appear in logs.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Any

from aidev_github import GitHubClient
from aidev_github.models import CommitInput
from aidev_rules_engine import Evaluator, RuleViolation
from aidev_shared import AgentRole, TaskPhase

from agent_runner.agents import (
    FrontendAgent,
    PlannerAgent,
    SecurityReviewerAgent,
)
from agent_runner.agents.base import AgentResult, FileChange
from agent_runner.config import AgentRunnerConfig
from agent_runner.db import (
    Repository,
    Task,
    TaskFile,
    TaskLog,
    TaskMessage,
    session_scope,
)
from agent_runner.llm import LLMClient

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot make forward progress.

    Captured at the top of :func:`run_task_async` /
    :func:`resume_after_approval_async` and converted to a ``FAILED``
    task row.
    """


# --- public surface ----------------------------------------------------


async def run_task_async(
    task_id: str,
    *,
    config: AgentRunnerConfig | None = None,
    executor_factory: Callable[[], Any] | None = None,
    llm_factory: Callable[[AgentRunnerConfig], LLMClient | None] | None = None,
) -> dict[str, str]:
    """Run the pre-approval pipeline for ``task_id``.

    Returns ``{"task_id": ..., "phase": ...}`` describing the final
    phase. The function never raises — pipeline errors are converted
    to ``FAILED`` state on the task row.
    """
    cfg = config or AgentRunnerConfig.from_env()
    if not cfg.real_pipeline_active:
        # Defensive — the dispatcher should have caught this, but if a
        # stale Celery message hits a mock-mode worker we MUST refuse.
        logger.warning(
            "run_task_async: refusing to run task %s — real pipeline "
            "not active (pipeline=%s executor=%s)",
            task_id,
            cfg.agent_pipeline,
            cfg.sandbox_executor,
        )
        return {"task_id": task_id, "phase": "skipped"}

    snapshot = _load_task_snapshot(task_id, cfg)
    if snapshot is None:
        logger.error("run_task_async: task %s not found", task_id)
        return {"task_id": task_id, "phase": "failed"}
    if not snapshot.has_repository:
        _fail(task_id, cfg, "Task has no connected repository.")
        return {"task_id": task_id, "phase": "failed"}

    branch = _branch_name(snapshot.task_id, snapshot.title)
    llm = (llm_factory or _default_llm_factory)(cfg)

    try:
        await _run_pre_approval(
            snapshot=snapshot,
            branch=branch,
            cfg=cfg,
            llm=llm,
            executor_factory=executor_factory or _default_executor_factory,
        )
        return {"task_id": task_id, "phase": TaskPhase.AWAITING_APPROVAL.value}
    except Exception as exc:  # noqa: BLE001 — top-of-pipeline boundary
        logger.exception("run_task_async failed for task %s", task_id)
        _fail(task_id, cfg, f"Pipeline failed: {exc}")
        return {"task_id": task_id, "phase": "failed"}


async def resume_after_approval_async(
    task_id: str,
    *,
    config: AgentRunnerConfig | None = None,
    github_factory: Callable[[AgentRunnerConfig], GitHubClient] | None = None,
) -> dict[str, str]:
    """Run the post-approval pipeline for ``task_id``.

    Returns ``{"task_id": ..., "phase": ...}`` describing the final
    phase. Never raises — converts errors to ``FAILED``.
    """
    cfg = config or AgentRunnerConfig.from_env()
    if not cfg.real_pipeline_active:
        logger.warning(
            "resume_after_approval_async: refusing — real pipeline not active"
        )
        return {"task_id": task_id, "phase": "skipped"}
    if not cfg.github_configured:
        _fail(task_id, cfg, "GitHub credentials are not configured.")
        return {"task_id": task_id, "phase": "failed"}

    snapshot = _load_task_snapshot(task_id, cfg)
    if snapshot is None or not snapshot.has_repository:
        _fail(task_id, cfg, "Task or repository missing at resume time.")
        return {"task_id": task_id, "phase": "failed"}

    try:
        return await _run_post_approval(
            snapshot=snapshot,
            cfg=cfg,
            github_factory=github_factory or _default_github_factory,
        )
    except Exception as exc:  # noqa: BLE001 — top-of-pipeline boundary
        logger.exception("resume_after_approval_async failed for task %s", task_id)
        _fail(task_id, cfg, f"Post-approval failed: {exc}")
        return {"task_id": task_id, "phase": "failed"}


# --- private orchestration --------------------------------------------


async def _run_pre_approval(
    *,
    snapshot: _TaskSnapshot,
    branch: str,
    cfg: AgentRunnerConfig,
    llm: LLMClient | None,
    executor_factory: Callable[[], Any],
) -> None:
    """Walk the pre-approval phases inside a fresh sandbox session."""
    _record_branch(snapshot.task_id, cfg, branch)
    _record_log(
        snapshot.task_id,
        cfg,
        phase=TaskPhase.PLANNING,
        agent=AgentRole.PLANNER,
        message=(
            f"Real pipeline starting. Repo={snapshot.repository_full_name} "
            f"branch={branch}."
        ),
    )

    plan_result = PlannerAgent().plan(
        instruction=snapshot.instruction,
        title=snapshot.title,
        llm=llm,
    )
    _persist_agent_result(snapshot.task_id, cfg, TaskPhase.PLANNING, plan_result)
    plan = list(plan_result.output.get("plan") or [])

    frontend_result = FrontendAgent().code(
        instruction=snapshot.instruction,
        title=snapshot.title,
        plan=plan,
        slug=_slug(snapshot.title),
        llm=llm,
    )
    _persist_agent_result(
        snapshot.task_id, cfg, TaskPhase.FRONTEND_CODING, frontend_result
    )

    # Open the sandbox and write the proposed changes. The session
    # context manager is responsible for full resource cleanup
    # regardless of how this block exits.
    executor = executor_factory()
    async with executor.session(
        task_id=snapshot.task_id,
        initial_phase=TaskPhase.FRONTEND_CODING,
    ) as session:
        clone_url = _clone_url(snapshot.repository_full_name, cfg.github_token)
        clone_result = await session.clone_repo(
            git_url=clone_url,
            branch=snapshot.default_branch,
        )
        if clone_result.returncode != 0:
            raise PipelineError(
                "git clone failed (see proxy logs for the redacted URL)"
            )

        evaluator = await _load_evaluator(session)
        if evaluator is not None:
            session.set_evaluator(evaluator)

        await _apply_changes(
            session=session,
            cfg=cfg,
            task_id=snapshot.task_id,
            changes=frontend_result.changes,
        )

        # Best-effort install / test / build — failures are logged but
        # never fatal at v0.4. The operator reviews them in the diff.
        await _run_project_commands(session, snapshot.task_id, cfg)

        diff_text = await session.capture_diff()
        changed_paths = await session.capture_changed_files()
        _stage_file_contents(
            snapshot.task_id,
            cfg,
            changes=frontend_result.changes,
            diff_text=diff_text,
            changed_paths=changed_paths,
        )

    _transition_phase(
        snapshot.task_id, cfg, phase=TaskPhase.AWAITING_APPROVAL, agent=None
    )
    _record_log(
        snapshot.task_id,
        cfg,
        phase=TaskPhase.AWAITING_APPROVAL,
        agent=None,
        message=(
            "Sandbox torn down. Task waiting for human approval before any "
            "branch push or PR creation."
        ),
    )


async def _run_post_approval(
    *,
    snapshot: _TaskSnapshot,
    cfg: AgentRunnerConfig,
    github_factory: Callable[[AgentRunnerConfig], GitHubClient],
) -> dict[str, str]:
    """Post-approval flow: security review → push branch → open PR."""
    changes = _load_staged_changes(snapshot.task_id, cfg)
    if not changes:
        _fail(snapshot.task_id, cfg, "No staged file content found at resume.")
        return {"task_id": snapshot.task_id, "phase": "failed"}

    review = SecurityReviewerAgent().review(changes=changes)
    _persist_agent_result(
        snapshot.task_id, cfg, TaskPhase.SECURITY_REVIEW, review
    )
    if bool(review.output.get("blocked")):
        _transition_phase(
            snapshot.task_id, cfg, phase=TaskPhase.FAILED, agent=None
        )
        _record_log(
            snapshot.task_id,
            cfg,
            phase=TaskPhase.FAILED,
            agent=AgentRole.SECURITY_REVIEWER,
            level="error",
            message="Security review blocked the PR. No branch push, no PR.",
        )
        return {"task_id": snapshot.task_id, "phase": TaskPhase.FAILED.value}

    client = github_factory(cfg)
    pr_url, pr_number = await asyncio.to_thread(
        _push_branch_and_open_pr,
        client=client,
        cfg=cfg,
        snapshot=snapshot,
        changes=changes,
    )
    _record_pr(snapshot.task_id, cfg, url=pr_url, number=pr_number)
    _transition_phase(
        snapshot.task_id, cfg, phase=TaskPhase.PR_OPENED, agent=None
    )
    _record_log(
        snapshot.task_id,
        cfg,
        phase=TaskPhase.PR_OPENED,
        agent=None,
        message=f"PR opened: {pr_url}",
    )
    _transition_phase(snapshot.task_id, cfg, phase=TaskPhase.DONE, agent=None)
    _record_log(
        snapshot.task_id,
        cfg,
        phase=TaskPhase.DONE,
        agent=None,
        message="Task complete.",
    )
    return {"task_id": snapshot.task_id, "phase": TaskPhase.DONE.value}


# --- sandbox helpers ---------------------------------------------------


async def _apply_changes(
    *,
    session: Any,
    cfg: AgentRunnerConfig,
    task_id: str,
    changes: list[FileChange],
) -> None:
    """Write ``changes`` into the sandbox; respect the rules engine.

    ``session.write_file`` already runs the evaluator when one is
    attached. We catch :class:`RuleViolation` here so the log line is
    clearer than a bare traceback.
    """
    for change in changes:
        try:
            await session.write_file(change.path, change.content)
            _record_log(
                task_id,
                cfg,
                phase=TaskPhase.FRONTEND_CODING,
                agent=AgentRole.FRONTEND_DEVELOPER,
                message=f"Wrote {change.path} ({len(change.content)} bytes).",
            )
        except RuleViolation as exc:
            _record_log(
                task_id,
                cfg,
                phase=TaskPhase.FRONTEND_CODING,
                agent=AgentRole.FRONTEND_DEVELOPER,
                level="warn",
                message=(
                    f"Rules engine blocked write to {change.path}: "
                    f"{exc.decision.reason}"
                ),
            )

    # Commit on the sandbox side so the diff/changed_files commands
    # below see the changes as "tracked". Failures are non-fatal.
    await session.run("git config user.email agent-runner@aidev.local")
    await session.run("git config user.name 'aidev real-pipeline'")
    await session.run("git add -A")
    await session.run(
        "git -c color.ui=never commit -m 'aidev: frontend phase' --allow-empty"
    )


async def _run_project_commands(
    session: Any, task_id: str, cfg: AgentRunnerConfig
) -> None:
    """Best-effort install / test / build.

    These are logged but never fail the pipeline at v0.4 — many repos
    have no test suite at all, and the smoketest repo is intentionally
    minimal.
    """
    commands = (
        "test -f package.json && (pnpm install --frozen-lockfile || npm install) || true",
        "test -f package.json && (pnpm test --if-present || npm test --if-present) || true",
        "test -f package.json && (pnpm build --if-present || npm run build --if-present) || true",
    )
    for cmd in commands:
        result = await session.run(cmd, timeout=300)
        _record_log(
            task_id,
            cfg,
            phase=TaskPhase.FRONTEND_QA,
            agent=AgentRole.QA,
            level="info" if result.returncode == 0 else "warn",
            message=(
                f"$ {cmd}\n"
                f"exit={result.returncode} "
                f"stdout={len(result.stdout)}B stderr={len(result.stderr)}B"
            ),
        )


async def _load_evaluator(session: Any) -> Evaluator | None:
    """Load the cloned repo's ``.ai-rules/`` if present."""
    probe = await session.run("test -d .ai-rules && echo yes || echo no")
    if not probe.stdout.strip().endswith("yes"):
        return None
    try:
        listing = await session.run(
            "find .ai-rules -type f \\( -name '*.yaml' -o -name '*.yml' \\)"
        )
        names = [n.strip() for n in listing.stdout.splitlines() if n.strip()]
        if not names:
            return None
        with TemporaryDirectory(prefix="aidev-rules-") as tmp:
            for name in names:
                payload = await session.read_file(name)
                rel = name.replace(".ai-rules/", "", 1)
                rel_path = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(rel_path) or tmp, exist_ok=True)
                with open(rel_path, "wb") as f:
                    f.write(payload)
            return Evaluator.from_directory(tmp)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("could not load .ai-rules: %s", exc)
        return None


# --- DB persistence helpers -------------------------------------------


def _persist_agent_result(
    task_id: str,
    cfg: AgentRunnerConfig,
    phase: TaskPhase,
    result: AgentResult,
) -> None:
    """Apply phase + active_agent + log + chat message in one tx."""
    _transition_phase(task_id, cfg, phase=phase, agent=result.agent)
    _record_log(
        task_id,
        cfg,
        phase=phase,
        agent=result.agent,
        message=result.log_message,
    )
    if result.chat_message:
        _record_message(
            task_id, cfg, agent=result.agent, content=result.chat_message
        )


def _transition_phase(
    task_id: str,
    cfg: AgentRunnerConfig,
    *,
    phase: TaskPhase,
    agent: AgentRole | None,
) -> None:
    with session_scope(cfg) as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        task.phase = phase.value
        task.active_agent = agent.value if agent else None


def _record_log(
    task_id: str,
    cfg: AgentRunnerConfig,
    *,
    message: str,
    phase: TaskPhase | None = None,
    agent: AgentRole | None = None,
    level: str = "info",
) -> None:
    with session_scope(cfg) as db:
        sequence = db.query(TaskLog).filter(TaskLog.task_id == task_id).count()
        db.add(
            TaskLog(
                id=_uuid(),
                task_id=task_id,
                level=level,
                agent_role=agent.value if agent else None,
                phase=phase.value if phase else None,
                message=message,
                sequence=sequence,
            )
        )


def _record_message(
    task_id: str,
    cfg: AgentRunnerConfig,
    *,
    agent: AgentRole | None,
    content: str,
) -> None:
    with session_scope(cfg) as db:
        db.add(
            TaskMessage(
                id=_uuid(),
                task_id=task_id,
                role="assistant",
                agent_role=agent.value if agent else None,
                content=content,
            )
        )


def _record_branch(task_id: str, cfg: AgentRunnerConfig, branch: str) -> None:
    with session_scope(cfg) as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        task.branch_name = branch


def _record_pr(
    task_id: str, cfg: AgentRunnerConfig, *, url: str, number: int
) -> None:
    with session_scope(cfg) as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        task.pr_url = url
        task.pr_number = number


def _stage_file_contents(
    task_id: str,
    cfg: AgentRunnerConfig,
    *,
    changes: list[FileChange],
    diff_text: str,
    changed_paths: list[str],
) -> None:
    """Persist file content (base64) + diff snippet to ``task_files``.

    The post-approval pipeline reads these rows back when it pushes the
    branch, so we do NOT need to re-open a sandbox after approval.
    """
    paths_seen = {c.path for c in changes}
    with session_scope(cfg) as db:
        for change in changes:
            db.add(
                TaskFile(
                    id=_uuid(),
                    task_id=task_id,
                    path=change.path,
                    status=change.status,
                    lines_added=_count_added(change.content),
                    lines_removed=0,
                    diff_snippet=_diff_snippet_for(change.path, diff_text),
                    content_b64=base64.b64encode(
                        change.content.encode("utf-8")
                    ).decode("ascii"),
                )
            )
        # Track sandbox-reported paths we don't own (install side-effects).
        # The post-approval push only commits rows with non-NULL content_b64.
        for path in changed_paths:
            if path in paths_seen:
                continue
            db.add(
                TaskFile(
                    id=_uuid(),
                    task_id=task_id,
                    path=path,
                    status="modified",
                    lines_added=0,
                    lines_removed=0,
                    diff_snippet=_diff_snippet_for(path, diff_text),
                    content_b64=None,
                )
            )


def _load_staged_changes(
    task_id: str, cfg: AgentRunnerConfig
) -> list[FileChange]:
    out: list[FileChange] = []
    with session_scope(cfg) as db:
        rows = (
            db.query(TaskFile)
            .filter(TaskFile.task_id == task_id)
            .order_by(TaskFile.created_at)
            .all()
        )
        for row in rows:
            if not row.content_b64:
                continue
            try:
                content = base64.b64decode(row.content_b64).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            out.append(
                FileChange(path=row.path, content=content, status=row.status)
            )
    return out


def _fail(task_id: str, cfg: AgentRunnerConfig, message: str) -> None:
    with contextlib.suppress(Exception), session_scope(cfg) as db:
        task = db.get(Task, task_id)
        if task is not None:
            task.phase = TaskPhase.FAILED.value
            task.active_agent = None
            task.error_message = message
    with contextlib.suppress(Exception):
        _record_log(
            task_id, cfg, phase=TaskPhase.FAILED, level="error", message=message
        )


# --- GitHub push -------------------------------------------------------


def _push_branch_and_open_pr(
    *,
    client: GitHubClient,
    cfg: AgentRunnerConfig,
    snapshot: _TaskSnapshot,
    changes: list[FileChange],
) -> tuple[str, int]:
    owner, name = snapshot.repository_full_name.split("/", 1)
    base = snapshot.default_branch
    branch_ref = client.get_branch(owner, name, base)

    new_branch_name = _branch_name(snapshot.task_id, snapshot.title)
    # Idempotency: if the branch already exists, reuse it.
    try:
        client.create_branch(
            owner, name, new_branch=new_branch_name, from_sha=branch_ref.sha
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.info("create_branch returned %s (assuming branch exists)", exc)

    commit_files = [
        CommitInput(path=c.path, content=c.content) for c in changes
    ]
    client.create_commit(
        owner,
        name,
        branch=new_branch_name,
        parent_sha=branch_ref.sha,
        message=f"aidev: {snapshot.title}",
        files=commit_files,
    )

    body = cfg.pr_body_template.format(
        title=snapshot.title,
        instruction=snapshot.instruction,
        branch=new_branch_name,
        pipeline=cfg.agent_pipeline,
        executor=cfg.sandbox_executor,
    )
    pr = client.create_pull_request(
        owner,
        name,
        title=cfg.pr_title_template.format(title=snapshot.title),
        head=new_branch_name,
        base=base,
        body=body,
        draft=False,
    )
    return pr.html_url, pr.number


def _default_github_factory(cfg: AgentRunnerConfig) -> GitHubClient:
    if cfg.github_token:
        return GitHubClient(token=cfg.github_token)
    if (
        cfg.github_app_id
        and cfg.github_app_private_key_path
        and cfg.github_app_installation_id
    ):
        with open(cfg.github_app_private_key_path) as f:
            private_key = f.read()
        return GitHubClient(
            app_id=cfg.github_app_id,
            private_key=private_key,
            installation_id=cfg.github_app_installation_id,
        )
    raise PipelineError("no GitHub credentials configured")


# --- task snapshot -----------------------------------------------------


@dataclass(frozen=True)
class _TaskSnapshot:
    """Detached read of one task row + its repository row.

    We materialise the snapshot up-front so the rest of the pipeline
    doesn't hold a database session while it talks to Docker / the
    model server / GitHub.
    """

    task_id: str
    title: str
    instruction: str
    has_repository: bool
    repository_full_name: str
    default_branch: str


def _load_task_snapshot(
    task_id: str, cfg: AgentRunnerConfig
) -> _TaskSnapshot | None:
    with session_scope(cfg) as db:
        task = db.get(Task, task_id)
        if task is None:
            return None
        repo: Repository | None = None
        if task.repository_id:
            repo = db.get(Repository, task.repository_id)
        if repo is None:
            return _TaskSnapshot(
                task_id=task.id,
                title=task.title,
                instruction=task.instruction,
                has_repository=False,
                repository_full_name="",
                default_branch="main",
            )
        return _TaskSnapshot(
            task_id=task.id,
            title=task.title,
            instruction=task.instruction,
            has_repository=True,
            repository_full_name=repo.full_name,
            default_branch=repo.default_branch or "main",
        )


# --- misc helpers ------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    out = _SLUG_RE.sub("-", value.lower()).strip("-")
    return out[:48] or "task"


def _branch_name(task_id: str, title: str) -> str:
    short = task_id.replace("-", "")[:8]
    return f"aidev/task-{short}-{_slug(title)}"


def _clone_url(full_name: str, token: str | None) -> str:
    if token:
        return f"https://x-access-token:{token}@github.com/{full_name}.git"
    return f"https://github.com/{full_name}.git"


def _count_added(content: str) -> int:
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def _diff_snippet_for(path: str, diff_text: str) -> str:
    """Return the chunk of ``diff_text`` that references ``path``.

    Cheap: we slice from ``diff --git ... <path>`` to the next
    ``diff --git`` marker. If the path is not present, return an empty
    snippet.
    """
    marker = f"diff --git a/{path}"
    idx = diff_text.find(marker)
    if idx < 0:
        return ""
    next_idx = diff_text.find("diff --git ", idx + len(marker))
    return diff_text[idx:next_idx] if next_idx >= 0 else diff_text[idx:]


def _uuid() -> str:
    from uuid import uuid4

    return str(uuid4())


def _default_llm_factory(cfg: AgentRunnerConfig) -> LLMClient | None:
    try:
        return LLMClient(cfg)
    except Exception as exc:  # noqa: BLE001 — model is optional
        logger.warning("could not initialise LLMClient: %s", exc)
        return None


def _default_executor_factory() -> Any:
    from sandbox_runner.docker_executor import DockerSandboxExecutor

    return DockerSandboxExecutor()


# --- Celery sync wrappers ---------------------------------------------


def run_task_sync(task_id: str) -> dict[str, str]:
    """Synchronous wrapper used by the Celery task."""
    return asyncio.run(run_task_async(task_id))


def resume_after_approval_sync(task_id: str) -> dict[str, str]:
    """Synchronous wrapper used by the Celery task."""
    return asyncio.run(resume_after_approval_async(task_id))


__all__ = [
    "PipelineError",
    "resume_after_approval_async",
    "resume_after_approval_sync",
    "run_task_async",
    "run_task_sync",
]
