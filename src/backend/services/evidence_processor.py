"""Evidence document processing — summarise uploaded files and build session RAG.

Sprint 8g: Text files are summarised (via summariser LLM) and indexed for session-specific RAG.
Sprint 15: Images can optionally be described by the inference LLM (if it supports
vision and `multimodal_enabled` is on in LLM settings) and the description is indexed
into session RAG just like a text document. Falls back to "stored only" on any error.
"""

import base64
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("backend.evidence")

# Session-specific RAG indices (in-memory, keyed by token)
_session_indices: dict[str, Any] = {}
_session_indices_lock = threading.Lock()

# Text file extensions that get summarised + indexed
TEXT_EXTENSIONS = {".pdf", ".txt", ".md", ".doc", ".docx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Hard cap for image multimodal analysis. Base64 inflates by ~33%, so 5MB raw → ~7MB payload.
MAX_IMAGE_BYTES_FOR_VISION = 5 * 1024 * 1024

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _evidence_dir(token: str) -> Path:
    path = Path(f"/app/data/sessions/{token}/evidence")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence_context_path(token: str) -> Path:
    return Path(f"/app/data/sessions/{token}/evidence_context.json")


def _extract_text(file_path: Path) -> str | None:
    """Extract text content from a file. Returns None for unsupported types."""
    ext = file_path.suffix.lower()

    if ext in (".txt", ".md"):
        try:
            return file_path.read_text(errors="replace")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None

    if ext == ".pdf":
        try:
            from llama_index.readers.file import PDFReader
            reader = PDFReader()
            docs = reader.load_data(file_path)
            return "\n\n".join(doc.text for doc in docs if doc.text.strip())
        except Exception as e:
            logger.error(f"Failed to read PDF {file_path}: {e}")
            return None

    if ext in (".doc", ".docx"):
        try:
            from llama_index.readers.file import DocxReader
            reader = DocxReader()
            docs = reader.load_data(file_path)
            return "\n\n".join(doc.text for doc in docs if doc.text.strip())
        except Exception as e:
            logger.error(f"Failed to read DOCX {file_path}: {e}")
            return None

    return None


async def summarise_document(text: str, filename: str, settings: dict[str, Any]) -> str:
    """Generate a concise summary of a document using the summariser LLM.

    Sprint 17: uses fallback cascade (summariser → reporter → inference).
    """
    from src.services.llm_provider import llm, build_fallback_chain

    prompt_path = Path("/app/data/prompts/evidence_summary.md")
    if not prompt_path.exists():
        prompt_path = Path(__file__).parent.parent / "prompts" / "evidence_summary.md"

    if prompt_path.exists():
        prompt_text = prompt_path.read_text()
    else:
        prompt_text = (
            "Summarise the following document concisely. Focus on: key facts, dates, names, "
            "locations, and any evidence of labor rights issues. Keep the summary structured and factual."
        )

    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": f"Document: {filename}\n\n{text[:50000]}"},  # Cap at ~50k chars
    ]

    # Sprint 17: build fallback chain for summariser slot
    chain = build_fallback_chain(settings, "summariser")

    response = ""
    in_think = False
    async for token in llm.stream_chat_with_fallback(
        messages=messages,
        slot_configs=chain,
    ):
        response += token
        if "<think>" in response and not in_think:
            in_think = True
        if in_think and "</think>" in response:
            in_think = False
            response = response.split("</think>", 1)[-1]

    clean = response.strip()
    if not clean:
        raise RuntimeError(
            f"Summariser returned empty response for {filename} "
            f"(all slots in fallback chain failed to produce content)"
        )
    logger.info(f"Evidence summary generated for {filename}: {len(clean)} chars")
    return clean


async def describe_image(
    image_bytes: bytes,
    filename: str,
    mime_type: str,
    settings: dict[str, Any],
) -> str:
    """Describe an image using the inference LLM (vision-capable model required).

    Returns the textual description, or raises on failure (caller decides fallback).
    The inference slot is reused — there is no separate vision slot. The admin must
    have selected a vision-capable model AND turned on `multimodal_enabled`.
    """
    from src.services.llm_provider import llm

    if len(image_bytes) > MAX_IMAGE_BYTES_FOR_VISION:
        raise ValueError(
            f"Image {filename} is {len(image_bytes)} bytes, exceeds limit "
            f"({MAX_IMAGE_BYTES_FOR_VISION} bytes)"
        )

    prompt_path = Path("/app/data/prompts/image_description.md")
    if not prompt_path.exists():
        prompt_path = Path(__file__).parent.parent / "prompts" / "image_description.md"
    if prompt_path.exists():
        system_prompt = prompt_path.read_text()
    else:
        system_prompt = (
            "Describe the image factually and concisely. Transcribe any visible text "
            "verbatim. Do not speculate beyond what is visible."
        )

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Describe this image (filename: {filename})."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    provider = settings.get("inference_provider")
    model = settings.get("inference_model")
    temperature = float(settings.get("inference_temperature", 0.3))
    max_tokens = int(settings.get("inference_max_tokens", 1024))
    num_ctx = settings.get("inference_num_ctx") if provider == "ollama" else None

    response = ""
    in_think = False
    async for token in llm.stream_chat(
        messages=messages,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        num_ctx=num_ctx,
    ):
        response += token
        if "<think>" in response and not in_think:
            in_think = True
        if in_think and "</think>" in response:
            in_think = False
            response = response.split("</think>", 1)[-1]

    clean = response.strip()
    if not clean:
        raise RuntimeError(f"Image description for {filename} returned empty response")
    logger.info(f"Image description generated for {filename}: {len(clean)} chars")
    return clean


def build_session_index(token: str, file_path: Path, text: str):
    """Add a document to the session-specific RAG index."""
    try:
        from llama_index.core import VectorStoreIndex, Document, Settings
        from src.services.rag_service import _get_embed_model

        Settings.embed_model = _get_embed_model()
        Settings.llm = None

        doc = Document(text=text, metadata={"filename": file_path.name, "session": token})

        with _session_indices_lock:
            if token in _session_indices:
                # Add to existing index
                _session_indices[token].insert(doc)
            else:
                # Create new index
                _session_indices[token] = VectorStoreIndex.from_documents(
                    [doc], chunk_size=512, chunk_overlap=50
                )

        logger.info(f"Session RAG updated for {token}: added {file_path.name}")
    except Exception as e:
        logger.error(f"Failed to build session index for {token}: {e}")


def get_session_rag_chunks(token: str, query: str, top_k: int = 3) -> list[str]:
    """Retrieve relevant chunks from session-specific evidence documents."""
    with _session_indices_lock:
        index = _session_indices.get(token)

    if index is None:
        return []

    try:
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        return [node.get_content() for node in nodes if node.get_content().strip()]
    except Exception as e:
        logger.error(f"Session RAG retrieval failed for {token}: {e}")
        return []


def load_evidence_context(token: str) -> list[dict[str, str]]:
    """Load evidence summaries from disk (for context injection)."""
    path = _evidence_context_path(token)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def save_evidence_context(token: str, entries: list[dict[str, str]]):
    """Save evidence summaries to disk."""
    path = _evidence_context_path(token)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.rename(path)


async def process_upload(
    token: str,
    filename: str,
    file_bytes: bytes,
    settings: dict[str, Any],
) -> dict[str, str]:
    """Process an uploaded file: save, summarise (if text), index for session RAG.

    Returns {"filename": ..., "type": "text"|"image", "summary": ...}

    Sprint 16 hotfix: if an entry with the same filename already exists in
    evidence_context.json, treat this as a re-upload — fully clear the previous
    state (file, sibling summary, evidence_context entry, session RAG) before
    writing the new file. This keeps RAG and evidence_context idempotent and
    avoids duplicate chunks on retries.
    """
    evidence_dir = _evidence_dir(token)

    # Re-upload dedup: if we already have an entry for this filename, wipe it.
    existing_entries = load_evidence_context(token)
    if any(e.get("filename") == filename for e in existing_entries):
        logger.info(f"Re-upload detected for {filename} on {token}; clearing previous state")
        try:
            delete_evidence(token, filename)
        except Exception as e:
            logger.warning(f"Failed to fully clear previous state for {filename}: {e}")

    file_path = evidence_dir / filename
    file_path.write_bytes(file_bytes)
    logger.info(f"Evidence saved: {file_path}")

    ext = file_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        summary = ""
        if settings.get("multimodal_enabled"):
            mime_type = _IMAGE_MIME.get(ext, "image/jpeg")
            try:
                summary = await describe_image(file_bytes, filename, mime_type, settings)
                # Persist the description alongside the image and index it for session RAG
                summary_path = evidence_dir / f"{filename}.summary.md"
                summary_path.write_text(summary)
                build_session_index(token, file_path, summary)
            except Exception as e:
                logger.warning(
                    f"Image multimodal analysis failed for {filename} ({token}): {e}. "
                    f"Storing image without description."
                )
                summary = ""
        entry = {"filename": filename, "type": "image", "summary": summary}
        entries = load_evidence_context(token)
        entries.append(entry)
        save_evidence_context(token, entries)
        return entry

    # Text file: extract, summarise, index
    text = _extract_text(file_path)
    if not text:
        entry = {"filename": filename, "type": "text", "summary": f"[File received but text extraction failed. The document '{filename}' has been stored as evidence but its contents could not be read for analysis.]"}
        entries = load_evidence_context(token)
        entries.append(entry)
        save_evidence_context(token, entries)
        return entry

    # Summarise. If this raises (empty response, crashed model, context overflow),
    # propagate so `_handle_upload` emits `upload_error` to the frontend — the
    # chip goes to `error` and the user can retry or remove it. The file stays
    # on disk for audit (Sprint 8f principle: data in volume never auto-deletes)
    # but is NOT added to RAG or evidence_context, so it does not influence the
    # model until a successful re-upload overwrites it.
    try:
        summary = await summarise_document(text, filename, settings)
    except Exception as e:
        logger.error(f"Summarisation failed for {filename} ({token}): {e}")
        raise

    # Save summary to disk
    summary_path = evidence_dir / f"{filename}.summary.md"
    summary_path.write_text(summary)

    # Index for session RAG
    build_session_index(token, file_path, text)

    # Save to evidence context
    entry = {"filename": filename, "type": "text", "summary": summary}
    entries = load_evidence_context(token)
    entries.append(entry)
    save_evidence_context(token, entries)

    return entry


def clear_session_index(token: str):
    """Remove session RAG index from memory (called on archive/cleanup)."""
    with _session_indices_lock:
        _session_indices.pop(token, None)


def rebuild_session_index(token: str):
    """Rebuild the session RAG index from disk after a file is removed (Sprint 16).

    Drops the in-memory index and re-indexes every remaining evidence file:
      - text files: re-extract text and index
      - images with a sibling .summary.md: index the description
      - images without a description: skipped (not in RAG anyway)
    """
    clear_session_index(token)

    evidence_dir = _evidence_dir(token)
    for entry_path in sorted(evidence_dir.iterdir()):
        if not entry_path.is_file():
            continue
        if entry_path.suffix == ".md" and entry_path.name.endswith(".summary.md"):
            continue  # sibling summary, indexed via its source file below
        ext = entry_path.suffix.lower()
        try:
            if ext in TEXT_EXTENSIONS:
                text = _extract_text(entry_path)
                if text:
                    build_session_index(token, entry_path, text)
            elif ext in IMAGE_EXTENSIONS:
                summary_path = entry_path.with_name(f"{entry_path.name}.summary.md")
                if summary_path.exists():
                    summary = summary_path.read_text()
                    if summary.strip():
                        build_session_index(token, entry_path, summary)
        except Exception as e:
            logger.warning(f"Rebuild index: skipping {entry_path.name} for {token}: {e}")
    logger.info(f"Session RAG rebuilt for {token}")


def delete_evidence(token: str, filename: str):
    """Retract a previously uploaded file (Sprint 16 — Claude-Style attachment X button).

    Removes the file and its sibling .summary.md from disk, drops the entry from
    evidence_context.json, and rebuilds the session RAG index. Idempotent: missing
    files are treated as success. Filename is sanitised to prevent path traversal.
    """
    # Path traversal guard — only the basename is allowed
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ValueError(f"Invalid filename: {filename!r}")

    evidence_dir = _evidence_dir(token)
    file_path = evidence_dir / filename
    summary_path = evidence_dir / f"{filename}.summary.md"

    # Remove files (idempotent)
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"Deleted evidence file {file_path}")
        except OSError as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            raise
    if summary_path.exists():
        try:
            summary_path.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete summary {summary_path}: {e}")

    # Drop entry from evidence_context.json
    try:
        entries = load_evidence_context(token)
        new_entries = [e for e in entries if e.get("filename") != filename]
        if len(new_entries) != len(entries):
            save_evidence_context(token, new_entries)
    except Exception as e:
        logger.error(f"Failed to update evidence_context.json for {token}: {e}")

    # Rebuild session RAG so the deleted file no longer influences responses.
    # Failures here don't fail the whole delete — disk truth is what matters.
    try:
        rebuild_session_index(token)
    except Exception as e:
        logger.error(f"Session RAG rebuild after delete failed for {token}: {e}")
