"""Evidence document processing — summarise uploaded files and build session RAG.

Sprint 8g: Text files are summarised (via summariser LLM) and indexed for session-specific RAG.
Images are stored but not analyzed.
"""

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
    """Generate a concise summary of a document using the summariser LLM."""
    from src.services.llm_provider import llm

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

    # Use summariser model (lighter, faster)
    provider = settings.get("summariser_provider", settings.get("inference_provider"))
    model = settings.get("summariser_model", settings.get("inference_model"))

    response = ""
    in_think = False
    async for token in llm.stream_chat(
        messages=messages,
        provider=provider,
        model=model,
        temperature=0.3,
        max_tokens=1024,
        num_ctx=settings.get("summariser_num_ctx") if provider == "ollama" else None,
    ):
        response += token
        if "<think>" in response and not in_think:
            in_think = True
        if in_think and "</think>" in response:
            in_think = False
            response = response.split("</think>", 1)[-1]

    clean = response.strip()
    logger.info(f"Evidence summary generated for {filename}: {len(clean)} chars")
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
    """
    evidence_dir = _evidence_dir(token)
    file_path = evidence_dir / filename
    file_path.write_bytes(file_bytes)
    logger.info(f"Evidence saved: {file_path}")

    ext = file_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        # Store image but don't analyze
        entry = {"filename": filename, "type": "image", "summary": ""}
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

    # Summarise
    summary = await summarise_document(text, filename, settings)

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
