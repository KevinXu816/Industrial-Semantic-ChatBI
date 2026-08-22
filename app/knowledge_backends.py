"""Knowledge retrieval backends and optional vector DB adapters."""
from __future__ import annotations
import math
import os
from .secrets import resolve_bootstrap_secret
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from .knowledge_embeddings import HashingEmbeddingProvider, cosine_similarity
from .knowledge_store import KnowledgeStore


def _is_effective(payload: Dict[str, Any]) -> bool:
    if str(payload.get("status", "approved")).lower() != "approved": return False
    now=datetime.now(timezone.utc)
    def parse(v):
        if not v: return None
        try: return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
        except Exception: return None
    start=parse(payload.get("effective_from")); end=parse(payload.get("effective_to"))
    return (start is None or start <= now) and (end is None or now < end)

def _terms(text: str) -> set[str]:
    latin = re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())
    chinese = [c for c in (text or "") if "\u4e00" <= c <= "\u9fff"]
    return set(latin + chinese)


class KnowledgeBackend:
    name = "backend"
    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def health(self):
        return {"backend": self.name, "status": "ok"}
    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        return {"indexed": 0, "backend": self.name}


class LocalHybridBackend(KnowledgeBackend):
    name = "local_hybrid"
    def __init__(self, store: KnowledgeStore, embedder=None, lexical_weight: float = 0.6):
        self.store = store
        self.embedder = embedder or HashingEmbeddingProvider()
        self.lexical_weight = max(0.0, min(float(lexical_weight), 1.0))

    def search(self, query: str, top_k: int = 5, filters=None):
        filters = filters or {}
        qterms = _terms(query)
        qvec = self.embedder.embed(query)
        results = []
        for chunk in self.store.list_chunks():
            # Retrieval defaults to effective approved knowledge only.
            if not _is_effective(chunk):
                continue
            if any(str(chunk.get(k, "")) != str(v) for k, v in filters.items() if v not in (None, "")):
                continue
            dterms = _terms(" ".join([str(chunk.get("title", "")), str(chunk.get("text", "")), " ".join(map(str, chunk.get("tags", [])))]))
            overlap = len(qterms & dterms)
            lexical = overlap / max(1.0, math.sqrt(max(1, len(qterms)) * max(1, len(dterms))))
            vector = max(0.0, cosine_similarity(qvec, self.embedder.embed(chunk.get("text", ""))))
            score = self.lexical_weight * lexical + (1.0 - self.lexical_weight) * vector
            if score <= 0:
                continue
            results.append({**chunk, "retrieval_score": round(score, 4), "lexical_score": round(lexical, 4), "vector_score": round(vector, 4), "retrieval_backend": self.name})
        results.sort(key=lambda x: x["retrieval_score"], reverse=True)
        return results[:max(1, min(int(top_k), 50))]


class QdrantBackend(KnowledgeBackend):
    name = "qdrant"
    def __init__(self, embedder=None):
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("Qdrant backend requires: pip install -e '.[qdrant]'") from exc
        self.client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), api_key=resolve_bootstrap_secret("QDRANT_API_KEY_REF", "QDRANT_API_KEY") or None)
        self.collection = os.getenv("QDRANT_COLLECTION", "industrial_knowledge")
        self.embedder = embedder or HashingEmbeddingProvider()

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        from qdrant_client.models import Distance, PointStruct, VectorParams
        collections = [x.name for x in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(collection_name=self.collection, vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE))
        points = []
        for chunk in chunks:
            point_id = __import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, chunk["chunk_id"]).hex
            points.append(PointStruct(id=point_id, vector=self.embedder.embed(chunk.get("text", "")), payload=chunk))
        if points:
            self.client.upsert(collection_name=self.collection, points=points)
        return {"indexed": len(points), "backend": self.name, "collection": self.collection}

    def search(self, query: str, top_k: int = 5, filters=None):
        vector = self.embedder.embed(query)
        try:
            hits = self.client.search(collection_name=self.collection, query_vector=vector, limit=max(top_k * 3, top_k), with_payload=True)
        except AttributeError:
            hits = self.client.query_points(collection_name=self.collection, query=vector, limit=max(top_k * 3, top_k), with_payload=True).points
        out = []
        for h in hits:
            payload = dict(getattr(h, "payload", {}) or {})
            if not _is_effective(payload):
                continue
            if filters and any(str(payload.get(k, "")) != str(v) for k,v in filters.items() if v not in (None, "")):
                continue
            out.append({**payload, "retrieval_score": round(float(getattr(h, "score", 0)), 4), "retrieval_backend": self.name})
        return out[:max(1, min(int(top_k), 50))]

    def health(self):
        try:
            self.client.get_collections()
            return {"backend": self.name, "status": "ok", "collection": self.collection}
        except Exception as exc:
            return {"backend": self.name, "status": "error", "error": str(exc)}


class PgVectorBackend(KnowledgeBackend):
    name = "pgvector"
    def __init__(self, embedder=None):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("pgvector backend requires: pip install -e '.[pgvector]'") from exc
        self.psycopg = psycopg
        self.dsn = os.getenv("DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is required for pgvector backend")
        self.embedder = embedder or HashingEmbeddingProvider()
        self._ensure_schema()

    def _ensure_schema(self):
        with self.psycopg.connect(self.dsn) as conn:
            try:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(f"""CREATE TABLE IF NOT EXISTS knowledge_vectors(
                    chunk_id text PRIMARY KEY,
                    payload jsonb NOT NULL,
                    embedding vector({self.embedder.dimensions}) NOT NULL,
                    updated_at timestamptz DEFAULT now())""")
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise RuntimeError("pgvector extension must be installed and permitted in PostgreSQL") from exc

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        from psycopg.types.json import Jsonb
        with self.psycopg.connect(self.dsn) as conn:
            for chunk in chunks:
                vector = self.embedder.embed(chunk.get("text", ""))
                literal = "[" + ",".join(f"{x:.8f}" for x in vector) + "]"
                conn.execute("""INSERT INTO knowledge_vectors(chunk_id,payload,embedding) VALUES(%s,%s,%s::vector)
                    ON CONFLICT(chunk_id) DO UPDATE SET payload=EXCLUDED.payload, embedding=EXCLUDED.embedding, updated_at=now()""",
                    (chunk["chunk_id"], Jsonb(chunk), literal))
            conn.commit()
        return {"indexed": len(chunks), "backend": self.name}

    def search(self, query: str, top_k: int = 5, filters=None):
        vector = self.embedder.embed(query)
        literal = "[" + ",".join(f"{x:.8f}" for x in vector) + "]"
        with self.psycopg.connect(self.dsn) as conn:
            rows = conn.execute("""SELECT payload, 1 - (embedding <=> %s::vector) AS score
                                 FROM knowledge_vectors ORDER BY embedding <=> %s::vector LIMIT %s""",
                                (literal, literal, max(1, min(int(top_k) * 3, 150)))).fetchall()
        out=[]
        for r in rows:
            payload=dict(r[0])
            if not _is_effective(payload): continue
            if filters and any(str(payload.get(k, "")) != str(v) for k,v in filters.items() if v not in (None, "")): continue
            out.append({**payload, "retrieval_score": round(float(r[1]), 4), "retrieval_backend": self.name})
        return out[:max(1,min(int(top_k),50))]

    def health(self):
        try:
            with self.psycopg.connect(self.dsn) as conn:
                conn.execute("SELECT 1 FROM knowledge_vectors LIMIT 1")
            return {"backend": self.name, "status": "ok"}
        except Exception as exc:
            return {"backend": self.name, "status": "error", "error": str(exc)}


def get_knowledge_backend(store: KnowledgeStore) -> KnowledgeBackend:
    backend = os.getenv("KNOWLEDGE_BACKEND", "local").lower()
    if backend == "qdrant":
        return QdrantBackend()
    if backend in {"pgvector", "postgres-vector"}:
        return PgVectorBackend()
    return LocalHybridBackend(store)
