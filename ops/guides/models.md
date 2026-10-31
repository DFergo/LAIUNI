# Model recommendations

**As of 2026-10-31, from the HRDD Helper team's own testing.** Models change fast: check that a model is still offered (and its price) on the provider's site, and tell the user how old this list is.

| Use | Recommendation | Why |
|---|---|---|
| Best balance (quality, cost, speed) | **DeepSeek V4.1** | The most balanced model in our tests for this work. Via its own API (data processed in China) or through OpenRouter, where you can choose the serving provider and restrict to no-retention providers. |
| Privacy first, cloud | **Mistral** models (e.g. `mistral-large-4` for chat and reporter; a smaller Mistral model for compression) | EU provider. Prompt caching works well with this app (conversation excerpts are kept, so long chats are cheaper). |
| Local, 32–48 GB of memory | **Qwen3.6 27B** or **Gemma 4 31B** | Good results in our tests; run with LM Studio or Ollama, 4-bit quantization. |
| Embeddings | A multilingual embedding model **locally** (e.g. `bge-m3`, `qwen3-embedding`) | Runs on the GPU of almost any machine; much faster than the in-container fallback. |

Notes
- Same model for chat and reporter is fine; the reporter benefits from the strongest available.
- Reasoning ("thinking") models: reasoning tokens are billed and count against Max Tokens; leave Max Tokens blank or generous (see `docs/INSTALL.md` 4.4).
- Set a fallback for the chat (`inference_fallback_*`) on a different provider if the union depends on availability.
