"""Backend polling worker — pull-inverse loop, message routing, document generation.

Key invariant for internal documents:
    `_generate_document` always receives the FULL uncompressed conversation history.
    It calls `history.get_llm_messages()` which reads from the in-memory session cache,
    populated from `conversation.jsonl` at startup. The context compressor
    (`compress_if_needed` in context_compressor.py) is non-destructive — it returns a
    NEW message list used only by chat inference and never mutates the session store.
    Therefore `session_summary_uni.md`, `internal_case_file.md`, and the user-facing
    `summary.md` always see every user/assistant turn from the session.

    The only failure mode is the LLM truncating silently if the conversation exceeds
    the slot's `num_ctx`. `_generate_document` logs a WARNING when the estimated
    token count of the messages exceeds 90% of the configured `num_ctx`.
"""

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from src.services.frontend_registry import registry
from src.services.llm_provider import llm
from src.services.prompt_assembler import assemble_system_prompt
from src.services.rag_service import get_relevant_chunks
from src.services.evidence_processor import get_session_rag_chunks, load_evidence_context, process_upload
from src.services.session_store import store as history
from src.services.context_compressor import get_session_summary, load_session_summary
from src.services.context_compressor import compress_if_needed, estimate_messages_tokens
from src.services.smtp_service import (
    is_email_authorized, generate_auth_code, verify_auth_code,
    send_auth_code, is_configured as smtp_configured,
)
from src.services.guardrails import check_content, get_session_ended_response
from src.services.repetition_detector import RepetitionDetector
from src.api.v1.admin.llm import get_llm_settings

logger = logging.getLogger("backend.polling")

# Processing queue — messages waiting for LLM
_processing_queue: deque[dict[str, Any]] = deque()
_processing_lock = asyncio.Lock()
_is_processing = False


_branding_pushed: set[str] = set()  # Track which frontends have branding pushed


def invalidate_branding_cache(frontend_id: str = ""):
    """Clear branding push cache so it gets re-pushed on next poll."""
    if frontend_id:
        _branding_pushed.discard(frontend_id)
    else:
        _branding_pushed.clear()


async def _push_branding_if_needed(client: httpx.AsyncClient, url: str, fid: str):
    """Push branding config + translations to sidecar (once per session, or on change)."""
    if fid in _branding_pushed:
        return
    branding_path = Path(f"/app/data/campaigns/{fid}/branding.json")
    if not branding_path.exists():
        _branding_pushed.add(fid)
        return
    try:
        data = json.loads(branding_path.read_text())
        has_custom_text = bool(data.get("disclaimer_text") or data.get("instructions_text"))
        # Include translations if available
        from src.services.branding_translator import load_translations
        translations = load_translations(fid)
        payload = {**data, "custom": has_custom_text, "translations": translations}
        await client.post(f"{url}/internal/branding", json=payload)
        logger.info(f"Branding pushed to {fid}")
    except Exception as e:
        logger.debug(f"Branding push to {fid} failed: {e}")
        return  # Don't mark as pushed — retry next poll
    _branding_pushed.add(fid)


async def poll_frontends():
    """Poll all enabled frontends for pending messages."""
    client = httpx.AsyncClient(timeout=10.0)
    try:
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

                # Push branding config if exists (survives sidecar restarts)
                await _push_branding_if_needed(client, url, fid)

                for msg in messages:
                    msg["_frontend_url"] = url
                    msg["_frontend_name"] = frontend.get("name", "")
                    msg["_frontend_id"] = fid
                    async with _processing_lock:
                        _processing_queue.append(msg)
                    logger.info(f"Queued message {msg.get('message_id')} from {fid}")

                # Handle recovery requests (pull-inverse: backend resolves, pushes back)
                recovery_requests = data.get("recovery_requests", [])
                for token in recovery_requests:
                    await _handle_recovery(url, token)

                # Handle auth requests (pull-inverse: sidecar queues, backend resolves)
                auth_requests = data.get("auth_requests", [])
                for auth_req in auth_requests:
                    await _handle_auth_request(client, url, auth_req)

                # Handle file uploads — process each file silently.
                # Sprint 16: no automatic LLM response after upload. Files are
                # processed (extracted, summarised, indexed into session RAG,
                # recorded in evidence_context.json) and then "ship" with the
                # user's NEXT chat message via the existing chat pipeline.
                try:
                    while True:
                        upload_resp = await client.get(f"{url}/internal/uploads")
                        upload_resp.raise_for_status()
                        uploads = upload_resp.json().get("uploads", [])
                        if not uploads:
                            break
                        for upload in uploads:
                            tk = upload.get("session_token", "")
                            if not tk:
                                continue
                            upload["_frontend_id"] = fid
                            await _handle_upload(client, url, upload)
                except Exception as e:
                    logger.warning(f"Failed to poll uploads from {fid}: {e}")

                # Handle evidence deletion requests (Sprint 16 — Claude-Style retraction)
                try:
                    delete_requests = data.get("evidence_delete_requests", [])
                    for req in delete_requests:
                        await _handle_evidence_delete(
                            client, url, fid,
                            req.get("token", ""),
                            req.get("filename", ""),
                        )
                except Exception as e:
                    logger.warning(f"Failed to handle evidence deletions from {fid}: {e}")

            except Exception as e:
                registry.set_status(fid, "offline")
                logger.warning(f"Failed to poll {fid} ({url}): {e}")
    finally:
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

    async with httpx.AsyncClient(timeout=5.0) as client:
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


async def _safe_process(msg: dict[str, Any]):
    """Process a single message. Wrapped in try-except (lesson #2)."""
    frontend_url = msg.get("_frontend_url", "")
    frontend_name = msg.get("_frontend_name", "")
    frontend_id = msg.get("_frontend_id", "")
    session_token = msg.get("session_token", "")
    content = msg.get("content", "")
    survey = msg.get("survey")
    language = msg.get("language", "en")
    finalize = msg.get("finalize", False)
    # Sprint 16: filenames the user is "shipping" with this turn (chips)
    attachments = msg.get("attachments") or []
    if attachments:
        logger.info(f"[{session_token}] User turn ships with attachments: {attachments}")
        # File-only send: if the textarea was empty, use the attached filenames
        # as the user message content so history has a readable pivot point.
        if not content.strip():
            content = f"[Attached: {', '.join(attachments)}]"

    client = httpx.AsyncClient(timeout=30.0)
    try:
        # If first message with survey, build system prompt and store it
        if survey:
            system_prompt = assemble_system_prompt(survey, language, frontend_id)
            history.init_session(session_token, system_prompt, survey, language, frontend_name, frontend_id)

        # Finalize: generate summary instead of normal processing
        if finalize:
            await _finalize_session(client, frontend_url, session_token, language, frontend_id)
            return

        # Add user message to history
        history.add_message(session_token, "user", content)

        # Pre-LLM guardrails check (§13.1) — pattern-based, fixed response
        guardrail_result = check_content(content, language)
        if guardrail_result.triggered:
            from src.core.config import config as app_config
            violations = history.increment_guardrail_violations(session_token)
            logger.warning(
                f"[{session_token}] Guardrail triggered ({guardrail_result.category}), "
                f"violation {violations}/{app_config.guardrail_max_triggers}"
            )

            # Check if session should be ended
            if violations >= app_config.guardrail_max_triggers:
                # Flag and end session
                history.toggle_flag(session_token)
                ended_response = get_session_ended_response(language)
                history.add_message(session_token, "assistant", ended_response)
                history.set_status(session_token, "completed")
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": ended_response},
                )
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "done", "data": ended_response},
                )
                logger.warning(f"[{session_token}] Session ended — max guardrail violations reached")
                return

            # Return fixed response (skip LLM entirely)
            history.add_message(session_token, "assistant", guardrail_result.response)
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "token", "data": guardrail_result.response},
            )
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "done", "data": guardrail_result.response},
            )
            return

        # Build messages for LLM (system + conversation history)
        llm_messages = history.get_llm_messages(session_token)

        # Inject evidence context — summaries of uploaded documents (fixed context)
        evidence_entries = load_evidence_context(session_token)
        if evidence_entries:
            text_docs = [e for e in evidence_entries if e.get("type") == "text" and e.get("summary")]
            analysed_images = [e for e in evidence_entries if e.get("type") == "image" and e.get("summary")]
            unanalysed_images = [e for e in evidence_entries if e.get("type") == "image" and not e.get("summary")]
            parts = []
            if text_docs:
                parts.append("Documents uploaded by the user:")
                for e in text_docs:
                    parts.append(f"\n**{e['filename']}:**\n{e['summary']}")
            if analysed_images:
                parts.append("\nImages uploaded by the user (described by a vision model):")
                for e in analysed_images:
                    parts.append(f"\n**{e['filename']}:**\n{e['summary']}")
            if unanalysed_images:
                parts.append("\nImages uploaded (stored but not analyzed): " + ", ".join(e["filename"] for e in unanalysed_images))
            evidence_context = "\n".join(parts)
            llm_messages.insert(-1, {"role": "system", "content": evidence_context})

        # Inject RAG context — retrieve relevant document chunks for this message
        rag_chunks = get_relevant_chunks(content, frontend_id=frontend_id)
        # Also query session-specific evidence RAG
        session_rag_chunks = get_session_rag_chunks(session_token, content)
        all_chunks = rag_chunks + session_rag_chunks

        if all_chunks:
            rag_context = (
                "The following excerpts from reference documents may be relevant "
                "to the user's message. Use them to ground your response where applicable. "
                "Cite the source if you reference specific provisions.\n\n"
                + "\n\n---\n\n".join(all_chunks)
            )
            # Insert RAG context as a system message before the last user message
            llm_messages.insert(-1, {"role": "system", "content": rag_context})
            logger.debug(f"Injected {len(all_chunks)} RAG chunks ({len(session_rag_chunks)} from evidence) for {session_token}")

        # Compress context if approaching limit (ADR-009)
        settings = get_llm_settings(frontend_id)
        context_tokens = estimate_messages_tokens(llm_messages)
        logger.info(f"[{session_token}] Context size: {context_tokens} tokens ({len(llm_messages)} messages)")
        llm_messages = await compress_if_needed(llm_messages, settings, session_token)

        # Try LLM inference, fall back to mock if unavailable
        raw_response = ""
        visible_response = ""
        in_think = False
        rep_detector = RepetitionDetector()
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

                # Check for repetition loops before streaming
                if rep_detector.check(token):
                    logger.warning(f"[{session_token}] Repetition loop detected, stopping generation")
                    break

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

        # If repetition was detected, use cleaned output instead
        if rep_detector.triggered:
            visible_response = rep_detector.get_clean_output()
            logger.info(f"[{session_token}] Using trimmed response ({len(visible_response)} chars)")

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
    frontend_id: str = "",
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
        try:
            with open(summary_prompt_path) as f:
                summary_instruction = f.read()
        except OSError as e:
            logger.error(f"Cannot read summary prompt {summary_prompt_path}: {e}")
            summary_instruction = "Generate a brief summary of this session for the user."

        # Build messages: full conversation + summary instruction
        llm_messages = history.get_llm_messages(session_token)

        # Add language instruction
        lang_instruction = f"Generate the summary in the following language: {language}."
        llm_messages.append({"role": "user", "content": f"{summary_instruction}\n\n{lang_instruction}"})

        # Generate summary — uses reporter slot if toggle is enabled, else inference
        settings = get_llm_settings(frontend_id)
        summary_slot = "reporter" if settings.get("use_reporter_for_user_summary") else "inference"
        slot_cfg = _slot_settings(settings, summary_slot)
        logger.info(f"[{session_token}] Finalize summary via slot={summary_slot} ({slot_cfg['provider']}/{slot_cfg['model']})")
        raw_response = ""
        visible_response = ""
        in_think = False

        try:
            # Sprint 17: fallback cascade for finalize summary
            from src.services.llm_provider import build_fallback_chain
            chain = build_fallback_chain(settings, summary_slot)
            async for token in llm.stream_chat_with_fallback(
                messages=llm_messages,
                slot_configs=chain,
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
        except (ConnectionError, RuntimeError):
            logger.warning(f"No LLM for finalization of {session_token}, using placeholder")
            visible_response = "Session ended. No LLM available to generate summary."
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "token", "data": visible_response},
            )

        clean_response = visible_response.strip() if visible_response else raw_response.strip()

        # Save summary as conversation message (so it appears on recovery)
        history.add_message(session_token, "assistant", clean_response)

        # Save summary to disk (atomic: tmp + rename)
        session_dir = f"/app/data/sessions/{session_token}"
        os.makedirs(session_dir, exist_ok=True)
        summary_path = os.path.join(session_dir, "summary.md")
        try:
            tmp_path = summary_path + ".tmp"
            with open(tmp_path, "w") as f:
                f.write(clean_response)
            os.replace(tmp_path, summary_path)
            logger.info(f"Summary saved to {summary_path}")
        except OSError as e:
            logger.error(f"Failed to save summary for {session_token}: {e}")

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
        await _generate_internal_documents(session_token, language, mode, settings, frontend_id)

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
    frontend_id: str = "",
):
    """Generate internal documents after session closure (user doesn't see these)."""
    import os
    session_dir = f"/app/data/sessions/{session_token}"
    os.makedirs(session_dir, exist_ok=True)

    # 1. Internal UNI summary (always generated) — uses reporter slot
    try:
        uni_summary = await _generate_document(
            session_token, "session_summary_uni.md", language, settings, slot="reporter"
        )
        if uni_summary:
            path = os.path.join(session_dir, "internal_summary.md")
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write(uni_summary)
            os.replace(tmp, path)
            logger.info(f"Internal UNI summary saved: {path}")
    except Exception as e:
        logger.error(f"Internal UNI summary failed for {session_token}: {e}")

    # 2. Report (skipped for training mode)
    report_content = None
    if mode == "training":
        logger.info(f"Report skipped for {session_token} (training mode)")
    else:
        try:
            report_content = await _generate_document(
                session_token, "internal_case_file.md", language, settings, slot="reporter"
            )
            if report_content:
                path = os.path.join(session_dir, "report.md")
                tmp = path + ".tmp"
                with open(tmp, "w") as f:
                    f.write(report_content)
                os.replace(tmp, path)
                logger.info(f"Report saved: {path}")
        except Exception as e:
            logger.error(f"Report generation failed for {session_token}: {e}")

    # Sprint 9: Send email notifications (best-effort)
    try:
        from src.services.smtp_service import notify_admin_report, send_user_summary, send_user_report
        session_data = history.get_session(session_token)
        user_email = session_data.get("survey", {}).get("email", "") if session_data else ""

        if report_content:
            await notify_admin_report(session_token, report_content, frontend_id)

        if user_email and is_email_authorized(user_email):
            # Read summary from disk (saved by _finalize_session)
            import os
            summary_path = os.path.join(f"/app/data/sessions/{session_token}", "summary.md")
            summary_text = ""
            if os.path.exists(summary_path):
                with open(summary_path) as sf:
                    summary_text = sf.read()
            if summary_text:
                await send_user_summary(user_email, session_token, summary_text, language)
            if report_content:
                await send_user_report(user_email, session_token, report_content, language)
    except Exception as e:
        logger.warning(f"Email notification failed for {session_token}: {e}")


def _slot_settings(settings: dict[str, Any], slot: str) -> dict[str, Any]:
    """Resolve LLM settings for a given slot. Delegates to llm_provider.slot_settings."""
    from src.services.llm_provider import slot_settings
    return slot_settings(settings, slot)


async def _generate_document(
    session_token: str,
    prompt_file: str,
    language: str,
    settings: dict[str, Any],
    slot: str = "inference",
) -> str | None:
    """Generate a document using a prompt file + full conversation. Returns text or None.

    `slot` selects which LLM to use: 'inference' (default, for chat/user-facing) or 'reporter'
    (dedicated to internal_summary and report). Falls back to inference if slot settings are empty.
    """
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

    try:
        with open(prompt_path) as f:
            prompt_instruction = f.read()
    except OSError as e:
        logger.error(f"Cannot read prompt file {prompt_path}: {e}")
        return None

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
    slot_cfg = _slot_settings(settings, slot)

    # Token-budget safeguard: internal docs always see the full conversation; if it
    # exceeds 90% of the slot's num_ctx the model will silently truncate. Warn so the
    # admin can bump num_ctx for the relevant slot.
    try:
        slot_num_ctx = (
            settings.get(f"{slot}_num_ctx")
            or settings.get("inference_num_ctx")
            or 32768
        )
        est_tokens = estimate_messages_tokens(llm_messages)
        if est_tokens > slot_num_ctx * 0.9:
            logger.warning(
                f"[{session_token}] {prompt_file}: conversation ~{est_tokens} tokens "
                f"exceeds 90% of slot '{slot}' num_ctx ({slot_num_ctx}). "
                f"The model may truncate silently — consider raising {slot}_num_ctx."
            )
    except Exception as e:
        logger.debug(f"Token estimate failed for {session_token}: {e}")

    # Sprint 17: fallback cascade for document generation
    from src.services.llm_provider import build_fallback_chain
    chain = build_fallback_chain(settings, slot)
    logger.info(f"[{session_token}] Generating {prompt_file} via slot={slot} ({slot_cfg['provider']}/{slot_cfg['model']}), chain={[c['_slot_name'] for c in chain]}")
    raw_response = ""
    in_think = False

    async for token in llm.stream_chat_with_fallback(
        messages=llm_messages,
        slot_configs=chain,
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


async def _handle_auth_request(client: httpx.AsyncClient, frontend_url: str, auth_req: dict[str, Any]):
    """Handle an auth request from the sidecar (pull-inverse)."""
    session_token = auth_req.get("session_token", "")
    email = auth_req.get("email", "").lower().strip()
    code_attempt = auth_req.get("code", "")
    language = auth_req.get("language", "en")

    if not session_token:
        return

    try:
        if code_attempt:
            # Verification attempt
            valid = verify_auth_code(session_token, code_attempt)
            result = {
                "session_token": session_token,
                "status": "verified" if valid else "invalid_code",
                "email": email,
            }
        else:
            # Code request — check whitelist, generate code, send email
            if not is_email_authorized(email):
                result = {
                    "session_token": session_token,
                    "status": "not_authorized",
                    "email": email,
                }
                logger.info(f"Auth rejected: {email} not in whitelist")
            elif not smtp_configured():
                result = {
                    "session_token": session_token,
                    "status": "smtp_not_configured",
                    "email": email,
                }
                logger.warning(f"Auth request but SMTP not configured")
            else:
                code = generate_auth_code(session_token, email)
                sent = await send_auth_code(email, code, language)
                if sent:
                    result = {
                        "session_token": session_token,
                        "status": "code_sent",
                        "email": email,
                    }
                    logger.info(f"Auth code sent to {email} for {session_token}")
                else:
                    result = {
                        "session_token": session_token,
                        "status": "smtp_error",
                        "email": email,
                    }
                    logger.error(f"Failed to send auth code to {email}")

        await client.post(
            f"{frontend_url}/internal/auth/{session_token}/result",
            json=result,
        )
    except Exception as e:
        logger.error(f"Auth request handling failed: {e}")


async def _handle_upload(client: httpx.AsyncClient, frontend_url: str, upload: dict[str, Any]) -> dict[str, str] | None:
    """Fetch uploaded file from sidecar, process it, notify user via SSE. Returns result dict or None."""
    token = upload.get("session_token", "")
    filename = upload.get("filename", "")
    if not token or not filename:
        return None

    try:
        # Fetch file from sidecar
        resp = await client.get(f"{frontend_url}/internal/upload/{token}/{filename}")
        resp.raise_for_status()
        file_bytes = resp.content

        # Sprint 16: no `upload_received` SSE event — the frontend chip
        # transitions uploading→processing on the HTTP POST response, not on
        # a separate event from the backend.

        # Process the file — use per-frontend LLM if configured
        # frontend_id not directly available here, but _handle_upload is called
        # within poll_frontends loop where fid is known. Pass it via upload dict.
        settings = get_llm_settings(upload.get("_frontend_id", ""))
        result = await process_upload(token, filename, file_bytes, settings)

        # Confirm receipt — sidecar deletes temp file
        try:
            await client.delete(f"{frontend_url}/internal/upload/{token}/{filename}")
        except Exception:
            pass

        # Notify user: processing complete
        if result["type"] == "image":
            # Sprint 15: include the description (if multimodal_enabled produced one)
            # so the frontend can switch between "stored" and "analysed" wording.
            event_data = json.dumps({
                "filename": filename,
                "type": "image",
                "summary": (result.get("summary") or "")[:200],
            })
        else:
            event_data = json.dumps({"filename": filename, "type": "text", "summary": result.get("summary", "")[:200]})

        try:
            await client.post(
                f"{frontend_url}/internal/stream/{token}/chunk",
                json={"event": "upload_processed", "data": event_data},
            )
        except Exception:
            pass

        logger.info(f"Upload processed: {filename} for {token} ({result['type']})")
        return result

    except Exception as e:
        logger.error(f"Upload processing failed for {filename} ({token}): {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{token}/chunk",
                json={"event": "upload_error", "data": f"Failed to process {filename}"},
            )
        except Exception:
            pass
        return None


async def _handle_evidence_delete(
    client: httpx.AsyncClient,
    frontend_url: str,
    frontend_id: str,
    token: str,
    filename: str,
):
    """Handle a user's request to retract an uploaded file (Sprint 16).

    Deletes the file + its sibling summary from disk, drops the entry from
    evidence_context.json, and rebuilds the session RAG index so the model no
    longer "knows" about the file. Pushes SSE events back to the frontend.
    Idempotent: missing files are treated as success.
    """
    from src.services.evidence_processor import delete_evidence

    if not token or not filename:
        return

    # Notify the user that deletion is starting
    try:
        await client.post(
            f"{frontend_url}/internal/stream/{token}/chunk",
            json={"event": "evidence_deleting", "data": filename},
        )
    except Exception:
        pass

    # If a chat inference is currently running for this session, refuse.
    # The user will see evidence_delete_error and the frontend will retry.
    async with _processing_lock:
        busy = _is_processing and any(
            m.get("session_token") == token for m in _processing_queue
        )
    if busy:
        logger.info(f"[{token}] Evidence delete deferred for {filename}: busy")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{token}/chunk",
                json={"event": "evidence_delete_error", "data": json.dumps({
                    "filename": filename, "reason": "busy",
                })},
            )
        except Exception:
            pass
        return

    try:
        delete_evidence(token, filename)
        logger.info(f"[{token}] Evidence deleted: {filename}")
        await client.post(
            f"{frontend_url}/internal/stream/{token}/chunk",
            json={"event": "evidence_deleted", "data": filename},
        )
    except Exception as e:
        logger.error(f"[{token}] Evidence delete failed for {filename}: {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{token}/chunk",
                json={"event": "evidence_delete_error", "data": json.dumps({
                    "filename": filename, "reason": str(e),
                })},
            )
        except Exception:
            pass


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
