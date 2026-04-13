"""RAG service — document indexing and retrieval via LlamaIndex.

Indexes documents from /app/data/documents/ using sentence-transformers embeddings.
Persists the vector index to /app/data/rag_index/.
Sprint 8h: Per-campaign indexes in /app/data/campaigns/{frontend_id}/.
Provides get_relevant_chunks(query, top_k, frontend_id) for prompt injection.
"""

import json
import logging
import threading
from pathlib import Path

from src.core.config import config

logger = logging.getLogger("backend.rag")

# Lazy-loaded globals — LlamaIndex imports are heavy, only load when needed
_index = None
_embed_model = None
_index_lock = threading.Lock()
_initialized = False

# Per-campaign indexes (Sprint 8h)
_campaign_indexes: dict[str, any] = {}  # frontend_id -> VectorStoreIndex
_campaign_lock = threading.Lock()


def _docs_dir() -> Path:
    path = Path("/app/data/documents")
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


def _load_or_build_index():
    """Load existing index from disk, or build from documents if none exists."""
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

    if index_file.exists():
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
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json"}]

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
            _load_or_build_index()


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
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json"}]

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

    # Campaign-specific RAG
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
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json"}]

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
    doc_files = [f for f in docs_path.iterdir() if f.is_file() and f.suffix in {".md", ".txt", ".json"}]

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
    """List documents in a campaign's document directory."""
    docs_path = _campaign_docs_dir(frontend_id)
    docs = []
    for f in sorted(docs_path.iterdir()):
        if f.is_file() and f.suffix in {".md", ".txt", ".json"}:
            stat = f.stat()
            docs.append({"name": f.name, "size": stat.st_size, "modified": stat.st_mtime})
    return docs


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
