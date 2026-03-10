"""RAG service — document indexing and retrieval via LlamaIndex.

Indexes documents from /app/data/documents/ using sentence-transformers embeddings.
Persists the vector index to /app/data/rag_index/.
Provides get_relevant_chunks(query, top_k) for prompt injection.
"""

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


def get_relevant_chunks(query: str, top_k: int | None = None) -> list[str]:
    """Retrieve the most relevant document chunks for a query.

    This is the single integration point with the rest of the system.
    Returns a list of text strings (chunks) sorted by relevance.
    """
    if not _initialized:
        initialize()

    if _index is None:
        return []

    if top_k is None:
        top_k = config.rag_similarity_top_k

    try:
        retriever = _index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        chunks = [node.get_content() for node in nodes if node.get_content().strip()]
        logger.debug(f"RAG retrieved {len(chunks)} chunks for query: {query[:80]}...")
        return chunks
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        return []


def get_index_stats() -> dict:
    """Get index statistics for admin display."""
    if not _initialized:
        initialize()

    if _index is None:
        return {"status": "empty", "node_count": 0}

    try:
        node_count = len(_index.docstore.docs) if hasattr(_index, 'docstore') else 0
        return {"status": "indexed", "node_count": node_count}
    except Exception:
        return {"status": "unknown", "node_count": 0}
