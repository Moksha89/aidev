"""Local-LLM client used by the v0.4 agent pipeline.

Wraps ``aidev-model-client`` (the OpenAI-compatible Chat Completions
client we already use elsewhere) and adds:

* graceful failure — if the model server is unreachable or returns
  garbage, the call raises :class:`LLMUnavailable` and the pipeline
  records the failure as a ``warning`` log instead of crashing the
  Celery task. Callers fall back to a deterministic template.
* JSON-shaped helper :meth:`generate_json` that strips Markdown
  fences and returns ``None`` on parse failure rather than raising.

The default target is the Ollama OpenAI-compatible endpoint
(``http://ollama:11434/v1`` inside docker-compose,
``http://localhost:11434/v1`` outside). The v0.4 readiness gate is
"works with local Ollama"; the hosted-LLM API key path is explicitly
out of scope.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from aidev_model_client import ChatMessage, ModelClient, ModelError

from .config import AgentRunnerConfig

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):  # noqa: N818 — intentional "Unavailable" suffix
    """Raised when the local model server cannot be reached or returns junk.

    Pipelines catch this and continue with a deterministic fallback so the
    real agent path is never *fully* dependent on the model server being
    up. The fallback files are still real (rules-engine validated, written
    through the sandbox) — they just contain the canned content rather
    than model-generated content.
    """


@dataclass(frozen=True)
class LLMReply:
    content: str
    model: str


class LLMClient:
    """Thin wrapper around :class:`aidev_model_client.ModelClient`."""

    def __init__(self, config: AgentRunnerConfig) -> None:
        self._config = config
        self._client = ModelClient(
            base_url=config.model_base_url,
            api_key=config.model_api_key,
            model=config.model_name,
            timeout_seconds=config.model_timeout_seconds,
        )

    # ---------------------------------------------------------- text

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int | None = 1024,
    ) -> LLMReply:
        """Return one chat reply or raise :class:`LLMUnavailable`."""
        messages: list[ChatMessage] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            reply = self._client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ModelError as exc:
            logger.warning("model server error: %s", exc)
            raise LLMUnavailable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — never crash the pipeline
            logger.warning("model client raised %s: %s", type(exc).__name__, exc)
            raise LLMUnavailable(str(exc)) from exc
        content = (reply.content or "").strip()
        if not content:
            raise LLMUnavailable("empty content from model server")
        return LLMReply(content=content, model=reply.model)

    # ---------------------------------------------------------- json

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int | None = 2048,
    ) -> dict | list | None:
        """Generate JSON, returning ``None`` on parse failure.

        Callers must always handle the ``None`` return; never block on
        the model producing parseable JSON.
        """
        try:
            reply = self.generate(
                system=system,
                user=user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMUnavailable:
            return None
        return _parse_json_loose(reply.content)


# --- helpers -----------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _parse_json_loose(text: str) -> dict | list | None:
    """Tolerant JSON parser for chatty model output.

    1. Try the raw string.
    2. Try the contents of the first ```json ... ``` fence.
    3. Try a balanced ``{...}`` / ``[...]`` substring scan.
    """
    text = text.strip()
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _candidates(text: str) -> list[str]:
    candidates: list[str] = [text]
    for match in _FENCE_RE.finditer(text):
        candidates.append(match.group(1).strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
    return candidates


__all__ = ["LLMClient", "LLMReply", "LLMUnavailable"]
