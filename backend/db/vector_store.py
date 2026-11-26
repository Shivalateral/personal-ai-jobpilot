"""ChromaDB vector store + SentenceTransformers PyTorch embedding wrapper with singleton caching."""

import hashlib
import logging
import math
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

# Force PyTorch backend in transformers to avoid Keras 3 / TensorFlow import conflicts
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
import numpy as np

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Provides dense text embeddings via SentenceTransformers (PyTorch) with deterministic fallback."""

    def __init__(self, model_name: Optional[str] = None, offline_fallback: Optional[bool] = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self.offline_fallback = (
            settings.embedding_offline_fallback if offline_fallback is None else offline_fallback
        )
        self._model = None
        self._using_fallback = False

    @property
    def backend_mode(self) -> str:
        self._load_model()
        return "deterministic_hash" if (self._using_fallback or self._model is None) else "sentence_transformers"

    def _load_model(self) -> None:
        if self._model is not None or self._using_fallback:
            return
        if self.offline_fallback:
            logger.info("Using deterministic offline embedding fallback (configured).")
            self._using_fallback = True
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, local_files_only=False)
            logger.info("Loaded SentenceTransformer PyTorch model: %s", self.model_name)
        except Exception as exc:
            logger.warning(
                "SentenceTransformer model '%s' unavailable (%s); falling back to deterministic hash embeddings.",
                self.model_name,
                exc,
            )
            self._using_fallback = True

    @staticmethod
    def _fallback_embed(text: str, dim: int = 384) -> List[float]:
        """Deterministic normalized feature-hashing embedding for offline/test environments."""
        vec = np.zeros(dim, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9+#.]+", (text or "").lower())
        if not tokens:
            vec[0] = 1.0
            return vec.tolist()

        grams = list(tokens) + [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign

        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def embed(self, text: str) -> List[float]:
        """Return a normalized embedding vector for a single text."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return normalized embedding vectors for a batch of texts."""
        if not texts:
            return []
        self._load_model()
        if self._using_fallback or self._model is None:
            return [self._fallback_embed(t) for t in texts]

        clipped = [t[:1400] for t in texts]
        vectors = self._model.encode(
            clipped,
            batch_size=128,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity clamped to [0.0, 1.0]."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        a = np.asarray(vec_a, dtype=np.float32)
        b = np.asarray(vec_b, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0 or math.isnan(denom):
            return 0.0
        sim = float(np.dot(a, b) / denom)
        return max(0.0, min(1.0, sim))


class VectorStore:
    """ChromaDB-backed vector store for resumes and discovered job descriptions."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        settings = get_settings()
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.embedding_service = embedding_service or get_embedding_service()
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.jobs_collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_jobs,
            metadata={"hnsw:space": "cosine"},
        )
        self.resumes_collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_resumes,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_resume(self, resume_id: int, document: str, metadata: Dict[str, Any]) -> List[float]:
        """Store or update the active resume embedding in ChromaDB."""
        embedding = self.embedding_service.embed(document)
        clean_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in metadata.items()}
        self.resumes_collection.upsert(
            ids=[f"resume_{resume_id}"],
            embeddings=[embedding],
            documents=[document[:8000]],
            metadatas=[clean_meta],
        )
        return embedding

    def upsert_job(self, job_id: int, document: str, metadata: Dict[str, Any]) -> List[float]:
        """Store or update a single job listing embedding in ChromaDB."""
        return self.upsert_jobs_batch([(job_id, document, metadata)])[0]

    def upsert_jobs_batch(self, items: List[tuple[int, str, Dict[str, Any]]]) -> List[List[float]]:
        """Batch-embed and upsert job listings into ChromaDB for high throughput."""
        if not items:
            return []
        docs = [doc[:8000] for _, doc, _ in items]
        embeddings = self.embedding_service.embed_batch(docs)
        ids = [f"job_{jid}" for jid, _, _ in items]
        metas = [
            {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in meta.items()}
            for _, _, meta in items
        ]
        # Upsert in chunks of 100 to respect Chroma batch limits
        chunk_size = 100
        for start in range(0, len(ids), chunk_size):
            end = start + chunk_size
            self.jobs_collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=docs[start:end],
                metadatas=metas[start:end],
            )
        return embeddings

    def get_job_embeddings(self, job_ids: List[int]) -> Dict[int, List[float]]:
        """Fetch pre-computed job embeddings from ChromaDB in chunks for fast re-scoring."""
        if not job_ids:
            return {}
        out: Dict[int, List[float]] = {}
        chunk_size = 500
        for start in range(0, len(job_ids), chunk_size):
            batch_ids = job_ids[start : start + chunk_size]
            res = self.jobs_collection.get(
                ids=[f"job_{jid}" for jid in batch_ids],
                include=["embeddings"],
            )
            ret_ids = res.get("ids") or []
            ret_embs = res.get("embeddings")
            if ret_embs is None:
                continue
            for idx, doc_id in enumerate(ret_ids):
                try:
                    jid = int(str(doc_id).replace("job_", ""))
                    emb = ret_embs[idx]
                    if emb is not None and len(emb) > 0:
                        out[jid] = list(emb)
                except Exception:
                    continue
        return out

    def query_similar_jobs(self, query_text: str, top_k: int = 8) -> List[Dict[str, Any]]:
        """Retrieve top-k semantically similar jobs from ChromaDB."""
        count = self.jobs_collection.count()
        if count == 0:
            return []
        query_emb = self.embedding_service.embed(query_text)
        result = self.jobs_collection.query(
            query_embeddings=[query_emb],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        items: List[Dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for idx, doc_id in enumerate(ids):
            dist = float(dists[idx]) if idx < len(dists) else 1.0
            items.append(
                {
                    "id": doc_id,
                    "job_id": int(metas[idx].get("job_id", 0)) if idx < len(metas) and metas[idx] else 0,
                    "document": docs[idx] if idx < len(docs) else "",
                    "metadata": metas[idx] if idx < len(metas) else {},
                    "similarity": max(0.0, min(1.0, 1.0 - dist)),
                }
            )
        return items


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Cached singleton EmbeddingService keeping the PyTorch model warm in memory."""
    return EmbeddingService()


@lru_cache
def get_vector_store() -> VectorStore:
    """Cached singleton VectorStore sharing the warm EmbeddingService."""
    return VectorStore(embedding_service=get_embedding_service())
