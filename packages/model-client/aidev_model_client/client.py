"""OpenAI-compatible Chat Completions client.

Designed to talk to Ollama / vLLM / llama.cpp-server / LM Studio. We
deliberately stick to the lowest common denominator of the OpenAI
protocol: `chat/completions` with `messages` and `stream`. We do not
use the Tool/Function Calling API yet because Ollama support is
inconsistent; tool use is implemented at the agent layer via
structured-output parsing of the assistant message.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass(frozen=True)
class ChatReply:
    content: str
    finish_reason: str
    model: str
    usage: dict[str, int]


@dataclass(frozen=True)
class ChatChunk:
    """A single streamed delta."""

    delta: str
    finish_reason: str | None
    raw: dict[str, Any]


class ModelError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Model server {status}: {message}")
        self.status = status


class ModelClient:
    """Sync, OpenAI-compatible chat completions client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        user_agent: str = "aidev-platform/0.1",
    ) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "ModelClient requires the 'httpx' package. "
                "Run `poetry add httpx` in the consuming service."
            ) from exc
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or "not-required"
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._user_agent = user_agent

    @property
    def model(self) -> str:
        return self._model

    # -------------------------------------------------------------- chat

    def chat(
        self,
        *,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ChatReply:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if stop:
            body["stop"] = stop
        if extra:
            body.update(extra)

        data = self._post_json("/chat/completions", body)
        choice = data["choices"][0]
        return ChatReply(
            content=choice["message"]["content"] or "",
            finish_reason=choice.get("finish_reason") or "stop",
            model=data.get("model") or self._model,
            usage=data.get("usage") or {},
        )

    def stream_chat(
        self,
        *,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Iterator[ChatChunk]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if stop:
            body["stop"] = stop
        if extra:
            body.update(extra)

        import httpx

        with httpx.Client(timeout=self._timeout) as client, client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=body,
        ) as resp:
            if resp.status_code >= 300:
                raise ModelError(resp.status_code, resp.read().decode("utf-8"))
            for line in resp.iter_lines():
                if not line:
                    continue
                payload = (
                    line[len("data:") :].strip()
                    if line.startswith("data:")
                    else line.strip()
                )
                if payload == "[DONE]":
                    return
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = (chunk.get("choices") or [{}])[0]
                delta = (choice.get("delta") or {}).get("content") or ""
                yield ChatChunk(
                    delta=delta,
                    finish_reason=choice.get("finish_reason"),
                    raw=chunk,
                )

    # ----------------------------------------------------------- helpers

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
        }

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        import httpx

        url = f"{self._base_url}{path}"
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(url, headers=self._headers(), json=body)
                if resp.status_code >= 500 and attempt < self._max_retries:
                    last_err = ModelError(resp.status_code, resp.text)
                    continue
                if resp.status_code >= 300:
                    raise ModelError(resp.status_code, resp.text)
                return resp.json()
            except httpx.HTTPError as exc:
                last_err = exc
                if attempt >= self._max_retries:
                    raise ModelError(0, str(exc)) from exc
        # Unreachable in practice, but keeps mypy happy.
        raise ModelError(0, str(last_err) if last_err else "unknown error")
