"""OpenAI-compatible chat completions client for the AI Developer platform."""

from aidev_model_client.client import (
    ChatChunk,
    ChatMessage,
    ChatReply,
    ModelClient,
    ModelError,
)

__all__ = [
    "ChatChunk",
    "ChatMessage",
    "ChatReply",
    "ModelClient",
    "ModelError",
]
__version__ = "0.1.0"
