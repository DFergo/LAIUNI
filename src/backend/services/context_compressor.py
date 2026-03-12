"""Context compression service — prevents context overflow in long conversations.

Uses incremental compression: a running summary is maintained and updated progressively
as the conversation grows. When inference context reaches the threshold, old messages
are replaced by the running summary.

Architecture: clean interface via compress_if_needed() to allow future Letta swap (ADR-009).
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.core.config import config

logger = logging.getLogger("backend.context_compressor")

# Token estimation: ~4 chars per token for English, ~3 for CJK/Arabic.
# Using 3.5 as a safe average across multilingual content.
_CHARS_PER_TOKEN = 3.5

# Default: preserve the last N messages (user + assistant) uncompressed
_DEFAULT_PRESERVE_RECENT = 4  # 4 messages = 2 exchanges

# Compression prompt loaded once
_compression_prompt: str | None = None

# Running summaries per session — maintained incrementally
# token -> {"summary": str, "compressed_up_to": int}
# compressed_up_to = index of last message included in the summary
_session_summaries: dict[str, dict[str, Any]] = {}


def _load_compression_prompt() -> str:
    """Load the compression prompt from data dir (editable) or defaults."""
    global _compression_prompt
    if _compression_prompt is not None:
        return _compression_prompt

    # Try data dir first (admin may have edited it)
    data_path = Path(config.prompts_path) / "context_compression.md"
    if data_path.exists():
        _compression_prompt = data_path.read_text().strip()
        return _compression_prompt

    # Fall back to built-in default
    default_path = Path(__file__).parent.parent / "prompts" / "context_compression.md"
    if default_path.exists():
        _compression_prompt = default_path.read_text().strip()
        return _compression_prompt

    logger.warning("Compression prompt not found, using minimal fallback")
    _compression_prompt = (
        "Summarize the following conversation. Preserve all names, dates, "
        "facts, companies, locations, and case details exactly as stated. "
        "Remove only greetings, repetitions, and verbose explanations."
    )
    return _compression_prompt


def estimate_tokens(text: str) -> int:
    """Estimate token count from text. Conservative (overestimates slightly)."""
    return int(len(text) / _CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total tokens for a list of messages.

    Includes overhead for role tags and message structure (~4 tokens per message).
    """
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content", "")) + 4
    return total


def _get_inference_budget(settings: dict[str, Any]) -> dict[str, int]:
    """Calculate inference context budget using progressive compression thresholds.

    Progressive compression: first compression at `compression_first_threshold` tokens,
    then every `compression_step_size` tokens after that.
    Example: first=20000, step=15000 → compress at 20k, 35k, 50k, 65k...
    """
    num_ctx = settings.get("inference_num_ctx", 32768)
    max_tokens = settings.get("inference_max_tokens", 2048)
    first_threshold = settings.get("compression_first_threshold", 20000)
    step_size = settings.get("compression_step_size", 15000)

    available = num_ctx - max_tokens

    return {
        "num_ctx": num_ctx,
        "max_tokens": max_tokens,
        "available": available,
        "first_threshold": first_threshold,
        "step_size": step_size,
    }


def _get_summariser_budget(settings: dict[str, Any]) -> int:
    """Get how many tokens we can send to the summariser in one pass.

    = summariser context window - compression prompt - response margin
    """
    summariser_ctx = settings.get("summariser_num_ctx", 8192)
    summariser_max_tokens = settings.get("summariser_max_tokens", 1024)
    prompt_overhead = 600  # compression prompt ~500 tokens + formatting
    return summariser_ctx - summariser_max_tokens - prompt_overhead


def _get_current_threshold(session_token: str, settings: dict[str, Any]) -> int:
    """Calculate the current compression threshold based on how many times we've compressed.

    Progressive: first at `first_threshold`, then every `step_size` after that.
    Example: first=20000, step=15000 → 20k, 35k, 50k, 65k...
    """
    budget = _get_inference_budget(settings)
    session_state = _session_summaries.get(session_token, {})
    compression_count = session_state.get("compression_count", 0)

    if compression_count == 0:
        return budget["first_threshold"]
    return budget["first_threshold"] + (compression_count * budget["step_size"])


def _needs_inference_compression(
    messages: list[dict[str, str]],
    settings: dict[str, Any],
    session_token: str = "",
) -> bool:
    """Check if inference context needs compression (progressive thresholds)."""
    if not settings.get("summariser_enabled", False):
        return False

    budget = _get_inference_budget(settings)
    current_tokens = estimate_messages_tokens(messages)
    threshold = _get_current_threshold(session_token, settings)

    # Safety: never exceed the model's context window
    hard_limit = budget["available"]
    if threshold > hard_limit:
        threshold = hard_limit

    logger.info(
        f"Inference context: {current_tokens} tokens, "
        f"next compression at: {threshold:,} tokens"
    )

    return current_tokens > threshold


def _needs_incremental_update(
    session_token: str,
    conversation: list[dict[str, str]],
    settings: dict[str, Any],
) -> bool:
    """Check if the running summary needs an incremental update.

    Triggers when uncompressed messages exceed 30% of summariser context.
    """
    session_state = _session_summaries.get(session_token, {})
    compressed_up_to = session_state.get("compressed_up_to", 0)

    # Messages not yet in the summary
    uncompressed = conversation[compressed_up_to:]
    if len(uncompressed) < 2:  # minimum 1 exchange before bothering
        return False

    summariser_budget = _get_summariser_budget(settings)
    uncompressed_tokens = estimate_messages_tokens(uncompressed)

    # Update summary when uncompressed messages hit 30% of summariser capacity
    return uncompressed_tokens > (summariser_budget * 0.30)


async def compress_if_needed(
    messages: list[dict[str, str]],
    settings: dict[str, Any],
    session_token: str = "",
) -> list[dict[str, str]]:
    """Compress conversation history if it exceeds the context threshold.

    Two-phase approach:
    1. Incremental: progressively update running summary as conversation grows
    2. Injection: when inference hits threshold, swap old messages for the summary

    Args:
        messages: full LLM message list [system, msg1, msg2, ..., latest_user_msg]
        settings: current LLM settings
        session_token: session identifier for tracking running summary

    Returns:
        Message list, potentially with old messages replaced by a summary.
    """
    if not settings.get("summariser_enabled", False):
        return messages

    # Separate system messages from conversation
    system_messages = []
    conversation = []
    for msg in messages:
        if msg["role"] == "system":
            system_messages.append(msg)
        else:
            conversation.append(msg)

    if len(conversation) < 2:  # need at least 1 exchange to compress
        return messages

    # Phase 1: Incremental summary update (runs in background, preparing for when we need it)
    if session_token and _needs_incremental_update(session_token, conversation, settings):
        await _update_running_summary(session_token, conversation, settings)

    # Phase 2: Check if inference needs compression NOW
    if not _needs_inference_compression(messages, settings, session_token):
        return messages

    # Get the running summary
    session_state = _session_summaries.get(session_token, {})
    summary = session_state.get("summary", "")

    if not summary:
        # No running summary yet — create one now from old messages
        to_compress = conversation[:-_DEFAULT_PRESERVE_RECENT]
        if not to_compress:
            return messages
        summary = await _compress_messages(to_compress, None, settings)
        if not summary:
            logger.warning("Compression returned empty, keeping original messages")
            return messages
        _session_summaries[session_token] = {
            "summary": summary,
            "compressed_up_to": len(conversation) - _DEFAULT_PRESERVE_RECENT,
            "compression_count": 1,
        }
        _persist_summary(session_token)

    compressed_up_to = session_state.get("compressed_up_to", 0)
    to_keep = conversation[compressed_up_to:]

    # If to_keep is still too many messages, keep only the most recent
    if len(to_keep) > _DEFAULT_PRESERVE_RECENT:
        to_keep = conversation[-_DEFAULT_PRESERVE_RECENT:]

    before_tokens = estimate_messages_tokens(messages)

    # Rebuild: system + summary + recent messages
    result = list(system_messages)
    result.append({
        "role": "system",
        "content": (
            "The following is a summary of the earlier part of this conversation. "
            "All names, dates, facts, and case details are preserved exactly as discussed. "
            "Continue the conversation naturally, referencing this context as needed.\n\n"
            + summary
        ),
    })
    result.extend(to_keep)

    after_tokens = estimate_messages_tokens(result)

    # Increment compression count for progressive thresholds
    current_state = _session_summaries.get(session_token, {})
    current_state["compression_count"] = current_state.get("compression_count", 0) + 1
    _session_summaries[session_token] = current_state
    _persist_summary(session_token)

    logger.info(
        f"Context compressed for {session_token}: "
        f"{before_tokens} → {after_tokens} tokens "
        f"({len(conversation)} msgs → summary + {len(to_keep)} recent) "
        f"[compression #{current_state['compression_count']}]"
    )

    return result


async def _update_running_summary(
    session_token: str,
    conversation: list[dict[str, str]],
    settings: dict[str, Any],
):
    """Incrementally update the running summary for a session.

    Takes the previous summary + new uncompressed messages → new summary.
    Each pass fits within the summariser's context window.
    """
    session_state = _session_summaries.get(session_token, {})
    previous_summary = session_state.get("summary", "")
    compressed_up_to = session_state.get("compressed_up_to", 0)

    # New messages since last compression
    new_messages = conversation[compressed_up_to:]
    if not new_messages:
        return

    # Keep some recent messages uncompressed for next time
    if len(new_messages) > _DEFAULT_PRESERVE_RECENT:
        to_compress = new_messages[:-_DEFAULT_PRESERVE_RECENT]
        new_compressed_up_to = compressed_up_to + len(to_compress)
    else:
        to_compress = new_messages
        new_compressed_up_to = compressed_up_to + len(to_compress)

    # Check if this batch fits in summariser context; if not, split into chunks
    summariser_budget = _get_summariser_budget(settings)
    previous_tokens = estimate_tokens(previous_summary) if previous_summary else 0
    batch_tokens = estimate_messages_tokens(to_compress)

    if (previous_tokens + batch_tokens) > summariser_budget:
        # Process in chunks that fit
        summary = previous_summary
        chunk: list[dict[str, str]] = []
        chunk_tokens = 0

        for msg in to_compress:
            msg_tokens = estimate_tokens(msg.get("content", "")) + 4
            if chunk_tokens + msg_tokens + previous_tokens > summariser_budget and chunk:
                # Compress this chunk
                summary = await _compress_messages(chunk, summary, settings)
                if summary:
                    previous_tokens = estimate_tokens(summary)
                chunk = []
                chunk_tokens = 0
            chunk.append(msg)
            chunk_tokens += msg_tokens

        # Compress remaining chunk
        if chunk:
            summary = await _compress_messages(chunk, summary, settings)
    else:
        # Fits in one pass
        summary = await _compress_messages(to_compress, previous_summary, settings)

    if summary:
        before_tokens = estimate_tokens(previous_summary) if previous_summary else 0
        after_tokens = estimate_tokens(summary)
        logger.info(
            f"Running summary updated for {session_token}: "
            f"{len(to_compress)} new messages compressed, "
            f"summary {before_tokens} → {after_tokens} tokens"
        )
        _session_summaries[session_token] = {
            "summary": summary,
            "compressed_up_to": new_compressed_up_to,
        }
        _persist_summary(session_token)


async def _compress_messages(
    messages: list[dict[str, str]],
    previous_summary: str | None,
    settings: dict[str, Any],
) -> str:
    """Call the LLM to compress messages into a summary.

    If previous_summary is provided, the summariser incorporates it
    (incremental compression).
    """
    from src.services.llm_provider import llm

    compression_prompt = _load_compression_prompt()
    conversation_text = _format_conversation(messages)

    user_content = ""
    if previous_summary:
        user_content = (
            "Previous summary of earlier conversation:\n\n"
            f"{previous_summary}\n\n"
            "---\n\n"
            "New messages to incorporate into the summary:\n\n"
            f"{conversation_text}"
        )
    else:
        user_content = f"Compress the following conversation:\n\n{conversation_text}"

    llm_messages = [
        {"role": "system", "content": compression_prompt},
        {"role": "user", "content": user_content},
    ]

    provider = settings.get("summariser_provider", "ollama")
    model = settings.get("summariser_model", "")
    temperature = settings.get("summariser_temperature", 0.3)
    max_tokens = settings.get("summariser_max_tokens", 1024)
    num_ctx = settings.get("summariser_num_ctx") if provider == "ollama" else None

    try:
        # Direct HTTP call — avoids stream conflicts with inference
        from src.core.config import config as app_config

        if provider == "ollama":
            endpoint = f"{app_config.ollama_endpoint}/v1/chat/completions"
        else:
            endpoint = f"{app_config.lm_studio_endpoint}/chat/completions"

        body: dict[str, Any] = {
            "model": model,
            "messages": llm_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if provider == "ollama" and num_ctx:
            body["options"] = {"num_ctx": num_ctx}

        logger.info(
            f"Compression request: provider={provider}, model={model}, "
            f"endpoint={endpoint}, msg_count={len(llm_messages)}, max_tokens={max_tokens}"
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            resp = await client.post(endpoint, json=body)
            if resp.status_code != 200:
                body_text = resp.text[:500]
                logger.error(
                    f"Compression HTTP {resp.status_code}: {body_text} — "
                    f"Request: model={model}, provider={provider}"
                )
                return ""
            data = resp.json()
            response = data["choices"][0]["message"]["content"]

        # Strip <think> blocks if present (Qwen3)
        if "<think>" in response:
            parts = response.split("</think>")
            if len(parts) > 1:
                response = parts[-1]

        return response.strip()

    except Exception as e:
        logger.error(f"Compression failed: {e}")
        return ""


def _format_conversation(messages: list[dict[str, str]]) -> str:
    """Format messages into readable text for the summariser."""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


def get_session_summary(session_token: str) -> str:
    """Get the running compression summary for a session (if any)."""
    state = _session_summaries.get(session_token)
    if state:
        return state.get("summary", "")
    # Try loading from disk
    summary_path = _session_summary_path(session_token)
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text())
            return data.get("summary", "")
        except Exception:
            pass
    return ""


def _session_summary_path(session_token: str) -> Path:
    return Path(config.sessions_path) / session_token / "compression_summary.json"


def _persist_summary(session_token: str):
    """Save running summary to disk."""
    state = _session_summaries.get(session_token)
    if not state or not state.get("summary"):
        return
    path = _session_summary_path(session_token)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, default=str))
    tmp.rename(path)


def load_session_summary(session_token: str):
    """Load running summary from disk into memory (on session recovery)."""
    path = _session_summary_path(session_token)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            _session_summaries[session_token] = data
            logger.info(f"Loaded compression summary for {session_token}")
        except Exception as e:
            logger.warning(f"Failed to load compression summary for {session_token}: {e}")


def clear_session(session_token: str):
    """Clear running summary for a session (on session close)."""
    _session_summaries.pop(session_token, None)
