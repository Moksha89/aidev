# Model Server Setup

The platform talks to any OpenAI-compatible Chat Completions endpoint.
Pick whichever runs best on your hardware.

## Recommended models by VRAM

| VRAM        | Recommended model                                | Notes                            |
| ----------- | ------------------------------------------------ | -------------------------------- |
| 8 GB        | `qwen2.5-coder:7b-instruct-q4_K_M`               | Fits Planner + small Frontend    |
| 12 GB       | `qwen2.5-coder:7b-instruct-q8_0`                 | Better code quality              |
| 16–24 GB    | `qwen2.5-coder:14b-instruct-q4_K_M`              | Sweet spot for the MVP           |
| 24–48 GB    | `qwen2.5-coder:32b-instruct-q4_K_M`              | Strong on multi-file edits       |
| 48–80 GB    | `deepseek-coder-v2:236b-lite-instruct-q4_K_M`    | Best frontier-class open coder   |
| 2× 80 GB    | `Qwen/Qwen2.5-Coder-32B-Instruct` (vLLM fp16)    | High-throughput multi-tenant     |

> **Tip:** the platform sends short, structured prompts (it does the
> orchestration itself), so context windows of 16k–32k are plenty. Don't
> burn VRAM on 128k-context variants unless you need them.

## Ollama (easiest)

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5-coder:14b
ollama list
```

Configure the platform:

```
MODEL_BASE_URL=http://host.docker.internal:11434/v1
MODEL_NAME=qwen2.5-coder:14b
MODEL_API_KEY=ollama              # any non-empty string; Ollama ignores it
```

If Ollama lives on a different host than the API container:

```
MODEL_BASE_URL=http://10.0.0.5:11434/v1
```

…and make sure `OLLAMA_HOST=0.0.0.0` is set on that host.

## vLLM (highest throughput)

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-14B-Instruct \
  --port 8001 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.9
```

Configure:

```
MODEL_BASE_URL=http://localhost:8001/v1
MODEL_NAME=Qwen/Qwen2.5-Coder-14B-Instruct
MODEL_API_KEY=any-string
```

vLLM exposes `/v1/chat/completions` with full SSE streaming, which the
agent worker uses to stream tokens to the dashboard.

## llama.cpp server

```bash
./server -m models/qwen2.5-coder-14b-instruct.Q4_K_M.gguf \
  --port 8002 --api --chat-template chatml
```

Configure `MODEL_BASE_URL=http://localhost:8002/v1`. Streaming works but
function-calling support varies — for now the platform doesn't use the
function-calling API, just plain chat completions with structured output
parsing.

## LM Studio (Windows / macOS dev)

Turn on **Local Server** in the GUI. Default port 1234. Configure
`MODEL_BASE_URL=http://localhost:1234/v1`.

## Multiple model servers per platform

Each project can pin its own model server via `/settings/models`. This is
useful when you want one fast model for the Planner and a larger one for
the Backend Developer. The schema:

```
model_servers:
  - id: planner
    base_url: http://localhost:11434/v1
    model: qwen2.5-coder:7b
  - id: developer
    base_url: http://localhost:8001/v1
    model: Qwen/Qwen2.5-Coder-32B-Instruct
```

The agent-runner resolves the right server per agent role; see
`workers/agent-runner/app/agents/__init__.py`.

## Reachability tips for the reference Ubuntu GPU host

- `nvidia-smi` to confirm the GPU is visible to the host.
- `sudo systemctl status ollama` then `curl http://localhost:11434/api/tags`.
- From inside a Docker container: `curl http://host.docker.internal:11434/v1/models`
  (requires Docker 20.10+; otherwise use the host IP).
- If the model server is behind a firewall, restrict it to the platform's
  Docker bridge subnet only — never expose `11434` or `8001` to the
  public internet.
