"""RAG service — document indexing and retrieval via LlamaIndex.

Indexes documents from DATA_DIR/config/documents/ using sentence-transformers embeddings.
Persists the vector index to the configured rag_index path.
Sprint 8h: Per-campaign indexes in DATA_DIR/campaigns/{frontend_id}/.
Provides get_relevant_chunks(query, top_k, frontend_id) for prompt injection.
"""

import json
import logging
import threading
from pathlib import Path

from src.core.config import config
from src.core.paths import DOCUMENTS_DIR

logger = logging.getLogger("backend.rag")

# Lazy-loaded globals — LlamaIndex imports are heavy, only load when needed
_index = None
_embed_model = None
_index_lock = threading.Lock()
_initialized = False

# Per-campaign indexes (Sprint 8h)
_campaign_indexes: dict[str, any] = {}  # frontend_id -> VectorStoreIndex
_campaign_lock = threading.Lock()

# Default RAG documents shipped with the app (Sprint 27) — seeded into the global
# docs dir on first run so a vanilla install ships with a coherent knowledge base.
_RAG_DEFAULTS_DIR = Path(__file__).parent.parent / "rag_defaults"
_SEED_SENTINEL = DOCUMENTS_DIR.parent / ".rag_seeded"  # config/.rag_seeded
_DOC_SUFFIXES = {".md", ".txt", ".json", ".pdf"}



def _docs_dir() -> Path:
    path = DOCUMENTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_dir() -> Path:
    path = Path(config.rag_index_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_embed_model():
    """Lazy-load the embedding model."""
    global _embed_model
    if _embed_model is None:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        _embed_model = HuggingFaceEmbedding(
            model_name=f"sentence-transformers/{config.rag_embedding_model}"
        )
        logger.info(f"Loaded embedding model: {config.rag_embedding_model}")
    return _embed_model


def _load_or_build_index(force_rebuild: bool = False):
    """Load existing index from disk, or build from documents if none exists.

    force_rebuild: skip loading a persisted index and rebuild from the source
    documents (used after first-run seeding adds new default docs).
    """
    global _index, _initialized

    from llama_index.core import (
        VectorStoreIndex,
        SimpleDirectoryReader,
        StorageContext,
        Settings,
        load_index_from_storage,
    )

    Settings.embed_model = _get_embed_model()
    # We don't use LlamaIndex's LLM — we handle that ourselves
    Settings.llm = None

    index_path = _index_dir()
    index_file = index_path / "index_store.json"

    if index_file.exists() and not force_rebuild:
        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(index_path))
            _index = load_index_from_storage(storage_context)
            doc_count = len(_index.docstore.docs) if hasattr(_index, 'docstore') else "?"
            logger.info(f"Loaded existing RAG index from {index_path} ({doc_count} nodes)")
            _initialized = True
            return
        except Exception as e:
            logger.warning(f"Failed to load existing index, rebuilding: {e}")

    # Build from documents
    docs_path = _docs_dir()
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json", ".pdf"}]

    if not doc_files:
        logger.info("No documents found — RAG index empty")
        _index = None
        _initialized = True
        return

    try:
        documents = SimpleDirectoryReader(str(docs_path)).load_data()
        _index = VectorStoreIndex.from_documents(
            documents,
            chunk_size=config.rag_chunk_size,
            chunk_overlap=50,
        )
        _index.storage_context.persist(persist_dir=str(index_path))
        logger.info(f"Built RAG index from {len(doc_files)} files, persisted to {index_path}")
    except Exception as e:
        logger.error(f"Failed to build RAG index: {e}")
        _index = None

    _initialized = True


def initialize():
    """Initialize the RAG index on startup. Call from lifespan."""
    with _index_lock:
        if not _initialized:
            seeded = seed_default_documents()
            _load_or_build_index(force_rebuild=bool(seeded))


def seed_default_documents() -> int:
    """First-run: copy the bundled default RAG documents into the global docs
    dir so a vanilla install ships with a coherent knowledge base.

    Runs once ever (guarded by a sentinel) and is non-destructive — it never
    overwrites an existing file, and never re-seeds after the admin has curated
    or emptied the set. Returns the number of files copied.
    """
    import shutil
    if _SEED_SENTINEL.exists():
        return 0
    docs_path = _docs_dir()
    copied = 0
    if _RAG_DEFAULTS_DIR.is_dir():
        for src in _RAG_DEFAULTS_DIR.iterdir():
            if src.is_file() and src.suffix in _DOC_SUFFIXES:
                dst = docs_path / src.name
                if not dst.exists():
                    try:
                        shutil.copyfile(src, dst)
                        copied += 1
                    except Exception as e:
                        logger.error(f"Failed to seed default RAG doc {src.name}: {e}")
    try:
        _SEED_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        _SEED_SENTINEL.write_text("seeded\n")
    except Exception as e:
        logger.error(f"Failed to write RAG seed sentinel: {e}")
    if copied:
        logger.info(f"Seeded {copied} default RAG document(s) into {docs_path}")
    return copied


def reset_documents_to_defaults() -> dict:
    """Restore the global RAG documents to the bundled factory set and reindex.

    Replaces the current global RAG documents with the shipped defaults, then
    rebuilds the index. Admin action (mirrors the prompt factory reset).
    """
    import shutil
    docs_path = _docs_dir()
    for f in list(docs_path.iterdir()):
        if f.is_file() and f.suffix in _DOC_SUFFIXES:
            try:
                f.unlink()
            except Exception as e:
                logger.error(f"Failed to remove doc {f.name} during reset: {e}")
    restored = 0
    if _RAG_DEFAULTS_DIR.is_dir():
        for src in _RAG_DEFAULTS_DIR.iterdir():
            if src.is_file() and src.suffix in _DOC_SUFFIXES:
                try:
                    shutil.copyfile(src, docs_path / src.name)
                    restored += 1
                except Exception as e:
                    logger.error(f"Failed to restore default RAG doc {src.name}: {e}")
    try:
        _SEED_SENTINEL.write_text("seeded\n")
    except Exception:
        pass
    result = reindex()
    result["restored"] = restored
    logger.info(f"Reset global RAG to factory defaults: restored {restored} document(s)")
    return result


def reindex() -> dict:
    """Rebuild the index from all documents. Called from admin reindex endpoint."""
    global _index, _initialized

    from llama_index.core import (
        VectorStoreIndex,
        SimpleDirectoryReader,
        Settings,
    )

    Settings.embed_model = _get_embed_model()
    Settings.llm = None

    docs_path = _docs_dir()
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json", ".pdf"}]

    if not doc_files:
        with _index_lock:
            _index = None
            _initialized = True
        # Clean old index
        index_path = _index_dir()
        for f in index_path.iterdir():
            if f.is_file():
                f.unlink()
        return {"status": "empty", "document_count": 0, "node_count": 0}

    try:
        documents = SimpleDirectoryReader(str(docs_path)).load_data()
        new_index = VectorStoreIndex.from_documents(
            documents,
            chunk_size=config.rag_chunk_size,
            chunk_overlap=50,
        )
        index_path = _index_dir()
        new_index.storage_context.persist(persist_dir=str(index_path))

        node_count = len(new_index.docstore.docs) if hasattr(new_index, 'docstore') else 0

        with _index_lock:
            _index = new_index
            _initialized = True

        logger.info(f"Reindexed: {len(doc_files)} files → {node_count} nodes")
        return {"status": "indexed", "document_count": len(doc_files), "node_count": node_count}

    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        return {"status": "error", "error": str(e), "document_count": len(doc_files)}


def get_relevant_chunks(query: str, top_k: int | None = None, frontend_id: str | None = None) -> list[str]:
    """Retrieve the most relevant document chunks for a query.

    Sprint 8h: If frontend_id is provided, also queries campaign-specific index.
    Campaign RAG config controls whether global RAG is included (default: yes).
    Returns a list of text strings (chunks) sorted by relevance.
    """
    if not _initialized:
        initialize()

    if top_k is None:
        top_k = config.rag_similarity_top_k

    chunks: list[str] = []

    # Global RAG — check if we should include it
    include_global = True
    if frontend_id:
        rag_config = get_campaign_rag_config(frontend_id)
        include_global = rag_config.get("include_global_rag", True)

    if include_global and _index is not None:
        try:
            retriever = _index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query)
            chunks.extend(node.get_content() for node in nodes if node.get_content().strip())
        except Exception as e:
            logger.error(f"Global RAG retrieval failed: {e}")

    # Campaign-specific RAG — Sprint 32: an active module's source files are
    # materialised into the frontend's own documents (see activate_module_rag),
    # so they are indexed and retrieved here like any other campaign document.
    if frontend_id:
        campaign_chunks = _get_campaign_chunks(frontend_id, query, top_k)
        chunks.extend(campaign_chunks)

    if chunks:
        logger.debug(f"RAG retrieved {len(chunks)} chunks for query: {query[:80]}... (frontend={frontend_id})")
    return chunks


# --- Campaign RAG (Sprint 8h) ---

def _campaign_docs_dir(frontend_id: str) -> Path:
    path = Path(f"/app/data/campaigns/{frontend_id}/documents")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _campaign_index_dir(frontend_id: str) -> Path:
    path = Path(f"/app/data/campaigns/{frontend_id}/rag_index")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _campaign_config_path(frontend_id: str) -> Path:
    return Path(f"/app/data/campaigns/{frontend_id}/rag_config.json")


def get_campaign_rag_config(frontend_id: str) -> dict:
    """Get campaign RAG config for a frontend."""
    config_path = _campaign_config_path(frontend_id)
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read campaign RAG config for {frontend_id}: {e}")
    return {"include_global_rag": True}


def set_campaign_rag_config(frontend_id: str, include_global_rag: bool) -> dict:
    """Set campaign RAG config for a frontend."""
    config_path = _campaign_config_path(frontend_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"include_global_rag": include_global_rag}
    config_path.write_text(json.dumps(data))
    logger.info(f"Campaign RAG config for {frontend_id}: include_global={include_global_rag}")
    return data


def reindex_campaign(frontend_id: str) -> None:
    """Drop and rebuild a campaign's RAG index (Sprint 24: after ZIP import).

    The index is not shipped in bundles — only the source documents — so it is
    removed and rebuilt from the imported documents.
    """
    import shutil
    idx = _campaign_index_dir(frontend_id)
    if idx.exists():
        shutil.rmtree(idx, ignore_errors=True)
    with _campaign_lock:
        _campaign_indexes.pop(frontend_id, None)
    try:
        _load_or_build_campaign_index(frontend_id)
        logger.info(f"Reindexed campaign RAG for {frontend_id}")
    except Exception as e:
        logger.warning(f"Campaign reindex for {frontend_id} failed (will lazy-build): {e}")


def _load_or_build_campaign_index(frontend_id: str):
    """Load or build campaign index for a frontend."""
    from llama_index.core import (
        VectorStoreIndex,
        SimpleDirectoryReader,
        StorageContext,
        Settings,
        load_index_from_storage,
    )

    Settings.embed_model = _get_embed_model()
    Settings.llm = None

    index_path = _campaign_index_dir(frontend_id)
    index_file = index_path / "index_store.json"

    if index_file.exists():
        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(index_path))
            idx = load_index_from_storage(storage_context)
            logger.info(f"Loaded campaign index for {frontend_id}")
            return idx
        except Exception as e:
            logger.warning(f"Failed to load campaign index for {frontend_id}, rebuilding: {e}")

    docs_path = _campaign_docs_dir(frontend_id)
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json", ".pdf"}]

    if not doc_files:
        return None

    try:
        documents = SimpleDirectoryReader(str(docs_path)).load_data()
        idx = VectorStoreIndex.from_documents(
            documents,
            chunk_size=config.rag_chunk_size,
            chunk_overlap=50,
        )
        idx.storage_context.persist(persist_dir=str(index_path))
        logger.info(f"Built campaign index for {frontend_id}: {len(doc_files)} files")
        return idx
    except Exception as e:
        logger.error(f"Failed to build campaign index for {frontend_id}: {e}")
        return None


def _get_campaign_chunks(frontend_id: str, query: str, top_k: int) -> list[str]:
    """Retrieve chunks from a campaign-specific index."""
    with _campaign_lock:
        if frontend_id not in _campaign_indexes:
            _campaign_indexes[frontend_id] = _load_or_build_campaign_index(frontend_id)

        idx = _campaign_indexes.get(frontend_id)

    if idx is None:
        return []

    try:
        retriever = idx.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        return [node.get_content() for node in nodes if node.get_content().strip()]
    except Exception as e:
        logger.error(f"Campaign RAG retrieval failed for {frontend_id}: {e}")
        return []


def reindex_campaign(frontend_id: str) -> dict:
    """Rebuild the campaign index for a frontend."""
    from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings

    Settings.embed_model = _get_embed_model()
    Settings.llm = None

    docs_path = _campaign_docs_dir(frontend_id)
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json", ".pdf"}]

    if not doc_files:
        with _campaign_lock:
            _campaign_indexes[frontend_id] = None
        # Clean old index
        index_path = _campaign_index_dir(frontend_id)
        for f in index_path.iterdir():
            if f.is_file():
                f.unlink()
        return {"status": "empty", "document_count": 0, "node_count": 0}

    try:
        documents = SimpleDirectoryReader(str(docs_path)).load_data()
        new_index = VectorStoreIndex.from_documents(
            documents,
            chunk_size=config.rag_chunk_size,
            chunk_overlap=50,
        )
        index_path = _campaign_index_dir(frontend_id)
        new_index.storage_context.persist(persist_dir=str(index_path))
        node_count = len(new_index.docstore.docs) if hasattr(new_index, 'docstore') else 0

        with _campaign_lock:
            _campaign_indexes[frontend_id] = new_index

        logger.info(f"Reindexed campaign {frontend_id}: {len(doc_files)} files → {node_count} nodes")
        return {"status": "indexed", "document_count": len(doc_files), "node_count": node_count}
    except Exception as e:
        logger.error(f"Campaign reindex failed for {frontend_id}: {e}")
        return {"status": "error", "error": str(e), "document_count": len(doc_files)}


def list_campaign_documents(frontend_id: str) -> list[dict]:
    """List documents in a campaign's document directory.

    Sprint 32: files materialised by an active module are flagged locked (and
    carry their owning module id) so the RAG panel can show them undeletable.
    """
    docs_path = _campaign_docs_dir(frontend_id)
    owner = {}
    for mid, files in get_module_docs_manifest(frontend_id).items():
        for name in files:
            owner[name] = mid
    docs = []
    for f in sorted(docs_path.iterdir()):
        if f.is_file() and f.suffix in {".md", ".txt", ".json", ".pdf"}:
            stat = f.stat()
            docs.append({
                "name": f.name, "size": stat.st_size, "modified": stat.st_mtime,
                "locked": f.name in owner, "module": owner.get(f.name),
            })
    return docs


# --- Feature-module RAG (Sprint 32) ---
# A module's source files are materialised into the frontend's own document set
# when the module is activated, and removed when it is deactivated. They index
# and retrieve exactly like a normal campaign document; the only difference is
# they are locked — the RAG panel cannot delete them while the module is on.
# A manifest records which files belong to which module.

def _module_manifest_path(frontend_id: str) -> Path:
    return Path(f"/app/data/campaigns/{frontend_id}/module_docs.json")


def get_module_docs_manifest(frontend_id: str) -> dict:
    """{module_id: [filename, ...]} of module-owned files in this frontend's RAG."""
    p = _module_manifest_path(frontend_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read module manifest for {frontend_id}: {e}")
    return {}


def _write_module_manifest(frontend_id: str, manifest: dict) -> None:
    p = _module_manifest_path(frontend_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest))


def locked_document_names(frontend_id: str) -> set[str]:
    """Filenames in this frontend's RAG owned by an active module (undeletable)."""
    names: set[str] = set()
    for files in get_module_docs_manifest(frontend_id).values():
        names.update(files)
    return names


def activate_module_rag(frontend_id: str, module_id: str) -> dict:
    """Copy a module's RAG source files into the frontend's documents, record them
    in the manifest, and reindex. Returns {"added": [...]}. Idempotent."""
    import shutil
    from src.services.modules import module_documents_dir

    src_dir = module_documents_dir(module_id)
    docs_dir = _campaign_docs_dir(frontend_id)
    added: list[str] = []
    if src_dir.is_dir():
        for f in sorted(src_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in _DOC_SUFFIXES:
                shutil.copy2(f, docs_dir / f.name)
                added.append(f.name)

    manifest = get_module_docs_manifest(frontend_id)
    manifest[module_id] = added
    _write_module_manifest(frontend_id, manifest)

    reindex_campaign(frontend_id)
    logger.info(f"Activated module {module_id} RAG for {frontend_id}: +{len(added)} files")
    return {"added": added}


def deactivate_module_rag(frontend_id: str, module_id: str) -> dict:
    """Remove a module's materialised files from the frontend's documents, drop it
    from the manifest, and reindex. Returns {"removed": [...]}."""
    manifest = get_module_docs_manifest(frontend_id)
    files = manifest.pop(module_id, [])
    docs_dir = _campaign_docs_dir(frontend_id)
    removed: list[str] = []
    for name in files:
        fp = docs_dir / name
        if fp.exists():
            fp.unlink()
            removed.append(name)
    _write_module_manifest(frontend_id, manifest)

    reindex_campaign(frontend_id)
    logger.info(f"Deactivated module {module_id} RAG for {frontend_id}: -{len(removed)} files")
    return {"removed": removed}


def get_index_stats() -> dict:
    """Get index statistics for admin display."""
    if not _initialized:
        initialize()

    if _index is None:
        return {"status": "empty", "node_count": 0}

    try:
        node_count = len(_index.docstore.docs) if hasattr(_index, 'docstore') else 0
        return {"status": "indexed", "node_count": node_count}
    except Exception as e:
        logger.warning(f"Failed to get index stats: {e}")
        return {"status": "unknown", "node_count": 0}
