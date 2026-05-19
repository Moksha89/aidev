"""Frontend Developer agent.

v0.4 implementation: produce a small but real frontend change set —
one Markdown deliverable and one Next.js page — that the pipeline
writes through the rules engine into the sandbox. The agent prefers
model-generated content but always returns a usable result via a
deterministic fallback when the local model is unavailable or its
output is unsafe.

Generation strategy:

1. Ask the LLM for a JSON object describing 1-3 file changes whose
   paths are in the v0.4 frontend allowlist.
2. Filter out forbidden paths (anything outside the allowlist) and
   anything that looks too large to be one safe write.
3. If filtering yields nothing usable, return the deterministic
   ``AIDEV_TASK.md`` + ``aidev_about/page.tsx`` pair. The fallback is
   intentionally tiny so the diff stays readable in the PR.

The rules engine ultimately decides whether a write is allowed; this
filter is a polite first pass that keeps the agent honest and the
worker logs short.
"""

from __future__ import annotations

import logging
import re
import textwrap

from aidev_shared import AgentRole

from agent_runner.agents.base import Agent, AgentResult, FileChange
from agent_runner.llm import LLMClient

logger = logging.getLogger(__name__)

_ALLOWED_PREFIXES: tuple[str, ...] = (
    "apps/web/src/",
    "apps/web/app/",
    "apps/web/components/",
    "apps/web/public/",
    "src/",
    "app/",
    "components/",
    "pages/",
    "styles/",
    "public/",
    "mocks/",
    "AIDEV_TASK.md",
    "TASK.md",
)
_ALLOWED_SUFFIXES: tuple[str, ...] = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".css",
    ".md",
)
_MAX_BYTES_PER_FILE = 16 * 1024


class FrontendAgent(Agent):
    role = AgentRole.FRONTEND_DEVELOPER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Frontend Developer agent.\n"
            "You write React/Next.js + Tailwind code only.\n"
            "Allowed paths: apps/web/src/**, apps/web/app/**, components/**,\n"
            "AIDEV_TASK.md (a short Markdown summary of the change set).\n"
            "Forbidden: anything under apps/api/**, backend/**, server/**,\n"
            "migrations/**, infra/**, docker/**, workers/**, .env*, secrets/**.\n"
            "Return strictly JSON: {\"files\": [{\"path\": str, \"content\": str}, ...]}.\n"
            "Each `content` must be < 8 KB. Do not include backend code.\n"
            "If you are unsure, return an empty `files` list and let the\n"
            "deterministic fallback take over."
        )

    def code(
        self,
        *,
        instruction: str,
        title: str,
        plan: list[dict],
        slug: str,
        llm: LLMClient | None,
    ) -> AgentResult:
        """Return the file changes that should be written into the sandbox.

        The pipeline routes every write through the rules engine; this
        method only proposes paths and content.
        """
        changes, used_model = _try_llm_files(
            instruction=instruction,
            title=title,
            plan=plan,
            slug=slug,
            llm=llm,
            system=self.system_prompt,
        )
        if not changes:
            changes = _default_changes(title=title, instruction=instruction, slug=slug)
            used_model = False

        summary_lines = ", ".join(c.path for c in changes)
        chat = (
            f"Frontend agent wrote {len(changes)} file(s): {summary_lines}.\n"
            "Lint/build will run next. Waiting for your approval before any "
            "backend changes."
        )
        return AgentResult(
            agent=self.role,
            log_message=(
                f"Frontend produced {len(changes)} change(s) "
                f"({'model' if used_model else 'fallback'})."
            ),
            chat_message=chat,
            changes=changes,
            used_model=used_model,
            output={"file_count": len(changes)},
        )


# --- helpers -----------------------------------------------------------


def _try_llm_files(
    *,
    instruction: str,
    title: str,
    plan: list[dict],
    slug: str,
    llm: LLMClient | None,
    system: str,
) -> tuple[list[FileChange], bool]:
    if llm is None:
        return [], False
    plan_text = "\n".join(f"  {i + 1}. {step['step']}" for i, step in enumerate(plan))
    user = (
        f"Title: {title}\n"
        f"Slug: {slug}\n\n"
        f"Instruction:\n{instruction}\n\n"
        f"Plan (frontend-only steps):\n{plan_text}\n\n"
        "Return JSON: {\"files\": [...]} where each file's `path` is\n"
        "inside the frontend allowlist."
    )
    parsed = llm.generate_json(system=system, user=user, max_tokens=2048)
    if not isinstance(parsed, dict):
        return [], False
    raw_files = parsed.get("files")
    if not isinstance(raw_files, list):
        return [], False
    cleaned: list[FileChange] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if not path or not content:
            continue
        if not _is_safe_path(path):
            continue
        if len(content.encode("utf-8")) > _MAX_BYTES_PER_FILE:
            continue
        cleaned.append(FileChange(path=path, content=content, status="added"))
        if len(cleaned) >= 3:
            break
    return cleaned, bool(cleaned)


def _is_safe_path(path: str) -> bool:
    if path.startswith("/") or ".." in path.split("/"):
        return False
    if any(path.startswith(p) for p in ("apps/api/", "workers/", "infra/", "docker/")):
        return False
    if any(path == p or path.startswith(p) for p in _ALLOWED_PREFIXES):
        return any(path.endswith(s) for s in _ALLOWED_SUFFIXES)
    return False


def _default_changes(
    *, title: str, instruction: str, slug: str
) -> list[FileChange]:
    safe_slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or "task"
    page_dir = f"apps/web/app/aidev/{safe_slug}"
    summary_md = textwrap.dedent(
        f"""
        # {title}

        This file was added by the AI Developer platform (real pipeline,
        frontend phase) as a proof-of-life change for the task above.

        ## Original instruction

        {instruction.strip()}

        ## Frontend deliverable

        A new Next.js page at `{page_dir}/page.tsx` renders the task
        title and instruction so a human reviewer can see the change in
        the preview before approving the backend phase.
        """
    ).strip() + "\n"
    page_tsx = textwrap.dedent(
        f"""
        export default function AidevTaskPage() {{
          const title = {title!r};
          const instruction = {instruction.strip()!r};
          return (
            <main className="mx-auto max-w-2xl p-8 space-y-4">
              <h1 className="text-2xl font-semibold">{{title}}</h1>
              <p className="text-sm text-muted-foreground">
                Generated by the AI Developer real pipeline (frontend phase).
              </p>
              <pre className="whitespace-pre-wrap rounded-md border p-4 text-sm">
        {{instruction}}
              </pre>
            </main>
          );
        }}
        """
    ).strip() + "\n"
    return [
        FileChange(path="AIDEV_TASK.md", content=summary_md, status="added"),
        FileChange(path=f"{page_dir}/page.tsx", content=page_tsx, status="added"),
    ]


__all__ = ["FrontendAgent"]
