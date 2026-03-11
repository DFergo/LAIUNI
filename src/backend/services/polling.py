import asyncio
import logging
from collections import deque
from typing import Any

import httpx

from src.services.frontend_registry import registry
from src.services.llm_provider import llm
from src.services.prompt_assembler import assemble_system_prompt
from src.services.rag_service import get_relevant_chunks
from src.services.session_store import store as history
from src.services.context_compressor import get_session_summary, load_session_summary
from src.services.context_compressor import compress_if_needed, estimate_messages_tokens
from src.api.v1.admin.llm import get_llm_settings

logger = logging.getLogger("backend.polling")

# Processing queue — messages waiting for LLM
_processing_queue: deque[dict[str, Any]] = deque()
_processing_lock = asyncio.Lock()
_is_processing = False


async def poll_frontends():
    """Poll all enabled frontends for pending messages."""
    client = httpx.AsyncClient(timeout=10.0)
    enabled = registry.list_enabled()

    for frontend in enabled:
        url = frontend["url"]
        fid = frontend["id"]
        try:
            resp = await client.get(f"{url}/internal/queue")
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("messages", [])
            registry.set_status(fid, "online")

            for msg in messages:
                msg["_frontend_url"] = url
                msg["_frontend_name"] = frontend.get("name", "")
                async with _processing_lock:
                    _processing_queue.append(msg)
                logger.info(f"Queued message {msg.get('message_id')} from {fid}")

            # Handle recovery requests (pull-inverse: backend resolves, pushes back)
            recovery_requests = data.get("recovery_requests", [])
            for token in recovery_requests:
                await _handle_recovery(url, token)

        except Exception as e:
            registry.set_status(fid, "offline")
            logger.warning(f"Failed to poll {fid} ({url}): {e}")

    await client.aclose()


async def process_queue():
    """Process one message at a time from the queue (sequential — LLM is single-threaded)."""
    global _is_processing

    async with _processing_lock:
        if _is_processing or not _processing_queue:
            return
        _is_processing = True

    try:
        # Send queue position updates to all waiting messages
        await _send_queue_positions()

        while True:
            async with _processing_lock:
                if not _processing_queue:
                    break
                msg = _processing_queue.popleft()

            # Update positions for remaining messages
            await _send_queue_positions()

            await _safe_process(msg)
    finally:
        async with _processing_lock:
            _is_processing = False


async def _send_queue_positions():
    """Notify each queued session of their position."""
    async with _processing_lock:
        items = list(_processing_queue)

    client = httpx.AsyncClient(timeout=5.0)
    for i, msg in enumerate(items):
        url = msg.get("_frontend_url", "")
        token = msg.get("session_token", "")
        if url and token:
            try:
                await client.post(
                    f"{url}/internal/stream/{token}/chunk",
                    json={"event": "queue_position", "data": str(i + 1)},
                )
            except Exception:
                pass
    await client.aclose()


async def _safe_process(msg: dict[str, Any]):
    """Process a single message. Wrapped in try-except (lesson #2)."""
    frontend_url = msg.get("_frontend_url", "")
    frontend_name = msg.get("_frontend_name", "")
    session_token = msg.get("session_token", "")
    content = msg.get("content", "")
    survey = msg.get("survey")
    language = msg.get("language", "en")
    finalize = msg.get("finalize", False)

    client = httpx.AsyncClient(timeout=30.0)
    try:
        # If first message with survey, build system prompt and store it
        if survey:
            system_prompt = assemble_system_prompt(survey, language)
            history.init_session(session_token, system_prompt, survey, language, frontend_name)

        # Finalize: generate summary instead of normal processing
        if finalize:
            await _finalize_session(client, frontend_url, session_token, language)
            return

        # Add user message to history
        history.add_message(session_token, "user", content)

        # Build messages for LLM (system + conversation history)
        llm_messages = history.get_llm_messages(session_token)

        # Inject RAG context — retrieve relevant document chunks for this message
        rag_chunks = get_relevant_chunks(content)
        if rag_chunks:
            rag_context = (
                "The following excerpts from reference documents may be relevant "
                "to the user's message. Use them to ground your response where applicable. "
                "Cite the source if you reference specific provisions.\n\n"
                + "\n\n---\n\n".join(rag_chunks)
            )
            # Insert RAG context as a system message before the last user message
            llm_messages.insert(-1, {"role": "system", "content": rag_context})
            logger.debug(f"Injected {len(rag_chunks)} RAG chunks for session {session_token}")

        # Compress context if approaching limit (ADR-009)
        settings = get_llm_settings()
        context_tokens = estimate_messages_tokens(llm_messages)
        logger.info(f"[{session_token}] Context size: {context_tokens} tokens ({len(llm_messages)} messages)")
        llm_messages = await compress_if_needed(llm_messages, settings, session_token)

        # Try LLM inference, fall back to mock if unavailable
        raw_response = ""
        visible_response = ""
        in_think = False
        try:
            async for token in llm.stream_chat(
                messages=llm_messages,
                provider=settings.get("inference_provider"),
                model=settings.get("inference_model"),
                temperature=settings.get("inference_temperature", 0.7),
                max_tokens=settings.get("inference_max_tokens", 2048),
                num_ctx=settings.get("inference_num_ctx") if settings.get("inference_provider") == "ollama" else None,
            ):
                raw_response += token

                # Filter <think>...</think> blocks (Qwen3 reasoning tokens)
                if "<think>" in raw_response and not in_think:
                    in_think = True
                if in_think:
                    if "</think>" in raw_response:
                        in_think = False
                        # Skip everything up to after </think> + whitespace
                        after = raw_response.split("</think>", 1)[-1]
                        raw_response = after
                    continue

                # Stream visible tokens to frontend
                visible_response += token
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": token},
                )
        except ConnectionError:
            # No LLM provider available — use mock response
            logger.warning(f"No LLM available for {session_token}, using mock")
            full_response = _mock_response(content)
            words = full_response.split(" ")
            for i, word in enumerate(words):
                t = word if i == 0 else " " + word
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": t},
                )
                await asyncio.sleep(0.05)

        # Strip think blocks from final response for history and done event
        clean_response = visible_response.strip() if visible_response else raw_response.strip()
        history.add_message(session_token, "assistant", clean_response)

        # Send done event
        await client.post(
            f"{frontend_url}/internal/stream/{session_token}/chunk",
            json={"event": "done", "data": clean_response},
        )
        logger.info(f"Processed message for session {session_token}")

    except Exception as e:
        logger.error(f"Processing failed for {session_token}: {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "error", "data": f"Processing error: {str(e)}"},
            )
        except Exception:
            pass
    finally:
        await client.aclose()


async def _finalize_session(
    client: httpx.AsyncClient,
    frontend_url: str,
    session_token: str,
    language: str,
):
    """Generate session summary, save to disk, mark session completed."""
    import os

    try:
        # Resolve per-profile summary prompt
        session = history.get_session(session_token)
        role = session.get("survey", {}).get("role", "worker") if session else "worker"
        prompt_file = f"session_summary_{role}.md"

        # Try /app/data/prompts first (custom), then built-in defaults
        summary_prompt_path = f"/app/data/prompts/{prompt_file}"
        if not os.path.exists(summary_prompt_path):
            summary_prompt_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "prompts", prompt_file
            )
        # Fallback to generic if profile-specific doesn't exist
        if not os.path.exists(summary_prompt_path):
            summary_prompt_path = "/app/data/prompts/session_summary.md"
            if not os.path.exists(summary_prompt_path):
                summary_prompt_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "prompts", "session_summary.md"
                )
        with open(summary_prompt_path) as f:
            summary_instruction = f.read()

        # Build messages: full conversation + summary instruction
        llm_messages = history.get_llm_messages(session_token)

        # Add language instruction
        lang_instruction = f"Generate the summary in the following language: {language}."
        llm_messages.append({"role": "user", "content": f"{summary_instruction}\n\n{lang_instruction}"})

        # Generate summary using inference LLM (not summariser)
        settings = get_llm_settings()
        raw_response = ""
        visible_response = ""
        in_think = False

        try:
            async for token in llm.stream_chat(
                messages=llm_messages,
                provider=settings.get("inference_provider"),
                model=settings.get("inference_model"),
                temperature=settings.get("inference_temperature", 0.7),
                max_tokens=settings.get("inference_max_tokens", 2048),
                num_ctx=settings.get("inference_num_ctx") if settings.get("inference_provider") == "ollama" else None,
            ):
                raw_response += token

                # Filter <think>...</think> blocks (Qwen3 reasoning tokens)
                if "<think>" in raw_response and not in_think:
                    in_think = True
                if in_think:
                    if "</think>" in raw_response:
                        in_think = False
                        after = raw_response.split("</think>", 1)[-1]
                        raw_response = after
                    continue

                visible_response += token
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": token},
                )
        except ConnectionError:
            logger.warning(f"No LLM for finalization of {session_token}, using placeholder")
            visible_response = "Session ended. No LLM available to generate summary."
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "token", "data": visible_response},
            )

        clean_response = visible_response.strip() if visible_response else raw_response.strip()

        # Save summary as conversation message (so it appears on recovery)
        history.add_message(session_token, "assistant", clean_response)

        # Save summary to disk
        session_dir = f"/app/data/sessions/{session_token}"
        os.makedirs(session_dir, exist_ok=True)
        summary_path = os.path.join(session_dir, "summary.md")
        with open(summary_path, "w") as f:
            f.write(clean_response)
        logger.info(f"Summary saved to {summary_path}")

        # Mark session as completed
        history.set_status(session_token, "completed")

        # Send done event (user is done — they can leave now)
        await client.post(
            f"{frontend_url}/internal/stream/{session_token}/chunk",
            json={"event": "done", "data": clean_response},
        )
        logger.info(f"Session {session_token} finalized — starting background documents")

        # Background: generate internal documents (user doesn't see these)
        mode = session.get("survey", {}).get("type", "documentation") if session else "documentation"
        await _generate_internal_documents(session_token, language, mode, settings)

    except Exception as e:
        logger.error(f"Finalization failed for {session_token}: {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "error", "data": f"Failed to generate summary: {str(e)}"},
            )
        except Exception:
            pass


async def _generate_internal_documents(
    session_token: str,
    language: str,
    mode: str,
    settings: dict[str, Any],
):
    """Generate internal documents after session closure (user doesn't see these)."""
    import os
    session_dir = f"/app/data/sessions/{session_token}"
    os.makedirs(session_dir, exist_ok=True)

    # 1. Internal UNI summary (always generated)
    try:
        uni_summary = await _generate_document(
            session_token, "session_summary_uni.md", language, settings
        )
        if uni_summary:
            path = os.path.join(session_dir, "internal_summary.md")
            with open(path, "w") as f:
                f.write(uni_summary)
            logger.info(f"Internal UNI summary saved: {path}")
    except Exception as e:
        logger.error(f"Internal UNI summary failed for {session_token}: {e}")

    # 2. Report (skipped for training mode)
    if mode == "training":
        logger.info(f"Report skipped for {session_token} (training mode)")
    else:
        try:
            report = await _generate_document(
                session_token, "internal_case_file.md", language, settings
            )
            if report:
                path = os.path.join(session_dir, "report.md")
                with open(path, "w") as f:
                    f.write(report)
                logger.info(f"Report saved: {path}")
        except Exception as e:
            logger.error(f"Report generation failed for {session_token}: {e}")


async def _generate_document(
    session_token: str,
    prompt_file: str,
    language: str,
    settings: dict[str, Any],
) -> str | None:
    """Generate a document using a prompt file + full conversation. Returns text or None."""
    import os

    # Load prompt
    prompt_path = f"/app/data/prompts/{prompt_file}"
    if not os.path.exists(prompt_path):
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "prompts", prompt_file
        )
    if not os.path.exists(prompt_path):
        logger.warning(f"Prompt file not found: {prompt_file}")
        return None

    with open(prompt_path) as f:
        prompt_instruction = f.read()

    # Build messages: replace system prompt with document prompt + full conversation
    llm_messages = history.get_llm_messages(session_token)

    # Replace the system prompt with the document generation prompt
    if llm_messages and llm_messages[0]["role"] == "system":
        llm_messages[0] = {"role": "system", "content": prompt_instruction}
    else:
        llm_messages.insert(0, {"role": "system", "content": prompt_instruction})

    # Add language instruction as final user message
    llm_messages.append({
        "role": "user",
        "content": f"Generate this document based on the conversation above. Write in: {language}.",
    })

    # Non-streaming LLM call
    raw_response = ""
    in_think = False

    async for token in llm.stream_chat(
        messages=llm_messages,
        provider=settings.get("inference_provider"),
        model=settings.get("inference_model"),
        temperature=settings.get("inference_temperature", 0.7),
        max_tokens=settings.get("inference_max_tokens", 2048),
        num_ctx=settings.get("inference_num_ctx") if settings.get("inference_provider") == "ollama" else None,
    ):
        raw_response += token

        # Filter <think>...</think> blocks
        if "<think>" in raw_response and not in_think:
            in_think = True
        if in_think:
            if "</think>" in raw_response:
                in_think = False
                raw_response = raw_response.split("</think>", 1)[-1]

    clean = raw_response.strip()
    logger.info(f"Document generated ({prompt_file}): {len(clean)} chars for {session_token}")
    return clean if clean else None


def _mock_response(content: str) -> str:
    return (
        f'Thank you for your message. You said: "{content}"\n\n'
        "This is a mock response. No LLM provider is currently available. "
        "Please configure LM Studio or Ollama in the admin panel."
    )


async def _handle_recovery(frontend_url: str, token: str):
    """Resolve a session recovery request and push data back to sidecar."""
    client = httpx.AsyncClient(timeout=10.0)
    try:
        session = history.get_session(token)
        if not session:
            await client.post(
                f"{frontend_url}/internal/session/{token}/recovery-data",
                json={"token": token, "status": "not_found", "data": None},
            )
            logger.info(f"Recovery: {token} not found")
            return

        # Check resume window (48h worker, 120h organizer)
        # Frontend type is determined by the frontend that's asking
        created_at = session.get("created_at")
        if created_at:
            from datetime import datetime, timezone
            try:
                created = datetime.fromisoformat(created_at)
                age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                # Use a generous default window; the frontend config has the real value
                # but we don't know which frontend type is asking.
                # Frontend will validate its own window. Backend uses 120h (max) as safety.
                if age_hours > 120:
                    await client.post(
                        f"{frontend_url}/internal/session/{token}/recovery-data",
                        json={"token": token, "status": "expired", "data": None},
                    )
                    logger.info(f"Recovery: {token} expired ({age_hours:.0f}h)")
                    return
            except Exception:
                pass

        # Build recovery data
        survey = session.get("survey", {})
        language = session.get("language", "en")
        session_status = session.get("status", "active")
        messages = session.get("messages", [])

        # Hybrid: compression summary if available, otherwise recent messages
        compression_summary = get_session_summary(token)

        if compression_summary:
            # Long conversation: send summary only
            recovery_data = {
                "survey": survey,
                "language": language,
                "role": survey.get("role", "worker"),
                "mode": survey.get("type", "documentation"),
                "status": session_status,
                "message_count": len(messages),
                "recovery_type": "summary",
                "summary": compression_summary,
            }
        else:
            # Short conversation: send all messages
            # Strip timestamps for frontend display
            clean_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ]
            recovery_data = {
                "survey": survey,
                "language": language,
                "role": survey.get("role", "worker"),
                "mode": survey.get("type", "documentation"),
                "status": session_status,
                "message_count": len(messages),
                "recovery_type": "full",
                "messages": clean_messages,
            }

        # Load compression summary into memory for continued conversation
        load_session_summary(token)

        await client.post(
            f"{frontend_url}/internal/session/{token}/recovery-data",
            json={"token": token, "status": "found", "data": recovery_data},
        )
        logger.info(f"Recovery: {token} resolved ({recovery_data['recovery_type']}, {len(messages)} msgs)")

    except Exception as e:
        logger.error(f"Recovery failed for {token}: {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/session/{token}/recovery-data",
                json={"token": token, "status": "not_found", "data": None},
            )
        except Exception:
            pass
    finally:
        await client.aclose()


async def polling_loop(interval: int = 2):
    """Main polling loop — runs as background task."""
    logger.info(f"Polling loop started (interval: {interval}s)")
    while True:
        try:
            await poll_frontends()
            await process_queue()
        except Exception as e:
            logger.error(f"Polling loop error: {e}")
        await asyncio.sleep(interval)
