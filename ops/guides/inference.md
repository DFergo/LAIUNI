# AI models: cloud providers or local models

The app is provider-neutral: the user chooses. Explain the trade-offs, then help them get an account/key or set up local models. Recommendations: guide `models`.

## What the app needs
| Slot | Job | Notes |
|---|---|---|
| **Inference** | The chat with users | The most important choice. Optional fallback model. |
| **Reporter** | Internal case file and session summary | Can be the same model; benefits from a strong one. |
| **Context compression** | Summarises long conversations and uploaded evidence | A smaller, cheaper model is fine. |
| **Translation** | Translates frontend texts (branding) | Any good multilingual model. |
| **Embeddings** | Knowledge-base search | A dedicated embedding model; best run locally (below). |

Each slot = a **connection** (address + key) + a **model**. Create connections once, then assign them.

## Privacy — say it plainly
With a cloud provider, the text of each conversation (testimonies, names, evidence) is sent to that provider. Ask what is acceptable (guide `onboarding`). Options, from most to least private: everything local · EU provider (e.g. Mistral) · a provider via OpenRouter restricted to providers that do not retain data (OpenRouter privacy settings: zero data retention) · any provider. A provider's own API in a country with weak data protection is the least private choice.

## Cloud: getting a key (the user signs up and pays)
| Provider | Sign up | Connection (`type`, `base_url`) |
|---|---|---|
| Mistral (France, EU) | https://console.mistral.ai → API keys | `openai`, `https://api.mistral.ai/v1` |
| OpenRouter (many models, one key) | https://openrouter.ai → Keys; set privacy preferences | `openai`, `https://openrouter.ai/api/v1` |
| DeepSeek (own API) | https://platform.deepseek.com | `openai`, `https://api.deepseek.com/v1` |
| Any OpenAI-compatible service | its console | `openai`, its `/v1` address |
| Anthropic | https://console.anthropic.com | `anthropic`, `https://api.anthropic.com` |
Most need prepaid credit. Suggest a spending limit in the provider's console.

Key handling: the user pastes the key into a local file (`~/.config/hrdd-ops/keys.env`, line `MISTRAL_API_KEY=...`), never in the chat. Then:
```
admin_api POST /admin/llm/connections
  {"id": "mistral", "type": "openai", "base_url": "https://api.mistral.ai/v1",
   "api_key": "env:~/.config/hrdd-ops/keys.env#MISTRAL_API_KEY"}
admin_api GET /admin/llm/connections/mistral/models      # check it works, list models
```

## Local models (machine with enough memory)
- **LM Studio** (https://lmstudio.ai, Mac/Windows/Linux, friendly UI): download a model, enable the local server (port 1234). Connection: `openai`, `http://host.docker.internal:1234/v1`.
- **Ollama** (https://ollama.com): `ollama pull <model>`. Connection: `ollama`, `http://host.docker.internal:11434`. For several users at once set `OLLAMA_NUM_PARALLEL` and `OLLAMA_KEEP_ALIVE=24h` (see `docs/INSTALL.md` 4.6).
- A new backend already has two connections, `lmstudio-default` (`http://host.docker.internal:1234/v1`) and `ollama-default` (`http://host.docker.internal:11434`): if LM Studio or Ollama runs on the backend machine (`check_machine` → `local_model_servers_running`), they work without adding anything.
- `host.docker.internal` = the machine running the backend container. A model server on another machine: use its LAN or Tailscale IP, and make the server listen on that address (Ollama: `OLLAMA_HOST=0.0.0.0`; LM Studio: "serve on local network").
- Memory guide: a 27–31B model at 4-bit quantization needs roughly 18–24 GB for the weights plus context — workable on 32–48 GB machines (Apple Silicon unified memory or a GPU with that much VRAM). Smaller machines: cloud chat model + local embeddings.

## Embeddings — run them locally
Almost any machine can run an embedding model on its GPU (Apple Silicon included) through Ollama or LM Studio; it makes the knowledge base much faster than the fallback model inside the container (CPU only). Use a **multilingual** embedding model (users write in many languages), e.g. `bge-m3` or `qwen3-embedding` in Ollama. After setting or changing it: `admin_api POST /admin/llm/embedding/reindex` (rebuilds the index; vectors of different models are incompatible).

## Assigning slots
```
admin_api PUT /admin/llm/settings
  {"inference_connection": "mistral", "inference_model": "<model id>",
   "reporter_connection": "mistral", "reporter_model": "<model id>",
   "summariser_connection": "...", "summariser_model": "...",
   "translation_connection": "...", "translation_model": "...",
   "embedding_connection": "ollama-local", "embedding_model": "bge-m3"}
admin_api GET /admin/llm/health
```
Only the fields sent are changed. Leave temperature / max tokens / context blank (provider defaults) unless there is a reason. `admin_api POST /admin/llm/capabilities` shows what a provider accepts for a slot. A frontend can use different models: `PUT /admin/frontends/{id}/llm-settings` (only the fields that differ).
