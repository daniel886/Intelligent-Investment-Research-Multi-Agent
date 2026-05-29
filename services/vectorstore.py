"""Chroma vector store wrapper for long-term memory of past reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from config.logging import logger


class ReportVectorStore:
    """Persistent Chroma collection storing report summaries + metadata."""

    COLLECTION = "research_reports"

    def __init__(self) -> None:
        self._client: Any = None
        self._collection: Any = None
        self._embed: Any = None
        self._init()

    def _init(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            persist_dir = Path(settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            # Try to load sentence-transformers first; if not available,
            # fall back to a no-op embedding function to avoid Chroma's
            # silent 80MB ONNX model download.
            embedding_function = None
            try:
                from sentence_transformers import SentenceTransformer  # noqa: F401

                self._embed = SentenceTransformer(settings.embedding_model)
                logger.info("Loaded SentenceTransformer: {}", settings.embedding_model)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "sentence-transformers unavailable ({}). Vector store will "
                    "store text only; semantic queries will fall back to text match.",
                    e,
                )
                self._embed = None

                # Provide a stub embedding fn that returns zero vectors so Chroma
                # doesn't try to download its default ONNX model.
                try:
                    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

                    class _ZeroEmbedding(EmbeddingFunction):
                        def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
                            return [[0.0] * 8 for _ in input]

                    embedding_function = _ZeroEmbedding()
                except Exception:  # noqa: BLE001
                    embedding_function = None

            kwargs: Dict[str, Any] = {"name": self.COLLECTION}
            if embedding_function is not None:
                kwargs["embedding_function"] = embedding_function
            self._collection = self._client.get_or_create_collection(**kwargs)
            logger.info("Chroma vector store ready @ {}", persist_dir)
        except Exception as e:  # noqa: BLE001
            logger.warning("Chroma init failed (vector memory disabled): {}", e)

    def _vec(self, text: str) -> Optional[List[float]]:
        if not self._embed or not text:
            return None
        try:
            return self._embed.encode(text, normalize_embeddings=True).tolist()
        except Exception as e:  # noqa: BLE001
            logger.warning("Embedding failed: {}", e)
            return None

    def add(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> bool:
        if not self._collection:
            return False
        emb = self._vec(text)
        try:
            kwargs: Dict[str, Any] = {
                "ids": [doc_id],
                "documents": [text[:8000]],
                "metadatas": [metadata],
            }
            if emb:
                kwargs["embeddings"] = [emb]
            self._collection.upsert(**kwargs)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Chroma upsert failed: {}", e)
            return False

    def query(self, text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        if not self._collection:
            return []
        emb = self._vec(text)
        try:
            kwargs: Dict[str, Any] = {"n_results": n_results}
            if emb:
                kwargs["query_embeddings"] = [emb]
            else:
                kwargs["query_texts"] = [text]
            res = self._collection.query(**kwargs)
            out: List[Dict[str, Any]] = []
            # Round-2 fix #7 (services/vectorstore.py:110): Chroma usually
            # returns ``{"ids": [[...]]}`` (one inner list per query), but on
            # an empty collection some versions return ``{"ids": []}``
            # (flattened). The previous ``res.get("ids", [[]])[0]`` then
            # raised IndexError. ``_first_or_empty`` handles both shapes.
            ids = self._first_or_empty(res.get("ids"))
            docs = self._first_or_empty(res.get("documents"))
            metas = self._first_or_empty(res.get("metadatas"))
            for i, d, m in zip(ids, docs, metas):
                out.append({"id": i, "document": d, "metadata": m})
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("Chroma query failed: {}", e)
            return []

    @staticmethod
    def _first_or_empty(value: Any) -> List[Any]:
        """Return the first inner list, or ``[]`` for any empty/flat result."""
        if not value:
            return []
        first = value[0]
        if isinstance(first, list):
            return first
        # Flat list — Chroma occasionally returns a 1-D list instead of 2-D.
        return list(value)


_singleton: Optional[ReportVectorStore] = None


def get_vector_store() -> ReportVectorStore:
    global _singleton
    if _singleton is None:
        _singleton = ReportVectorStore()
    return _singleton
