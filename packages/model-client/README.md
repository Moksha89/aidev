# @aidev/model-client

OpenAI-compatible chat completions client used by the agent-runner.

Supports any server that implements `/v1/chat/completions`:
**Ollama**, **vLLM**, **llama.cpp server**, **LM Studio**, etc.
No external API keys required — the client is configured via
`MODEL_BASE_URL`, `MODEL_API_KEY` (optional), and `MODEL_NAME`.

## Why a separate package?

So that the FastAPI process, the Celery worker, and any future sidecar
all import the same client with the same retries, timeout, and structured
logging behaviour. No silent forks.

## Usage

```python
from aidev_model_client import ModelClient

client = ModelClient(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    model="qwen2.5-coder:14b",
)

reply = client.chat(
    messages=[
        {"role": "system", "content": "You are a Frontend developer."},
        {"role": "user", "content": "Build a Tasks list page."},
    ],
    temperature=0.2,
)
print(reply.content)
```

For streaming:

```python
for chunk in client.stream_chat(messages=[...]):
    print(chunk.delta, end="", flush=True)
```
