"""Knowledge ingestion pipeline for FMEA/SOP/manual/maintenance documents."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List
from .knowledge_store import KnowledgeStore


class KnowledgeIngestionPipeline:
    def __init__(self, store: KnowledgeStore, backend=None):
        self.store = store
        self.backend = backend

    def ingest_documents(self, documents: Iterable[Dict[str, Any]], actor: str = "system", chunk_size: int = 420, overlap: int = 80):
        results = []
        for doc in documents:
            results.append(self.store.put_document(dict(doc), actor=actor, chunk_size=chunk_size, overlap=overlap))
        chunks = [c for r in results for c in r["chunks"]]
        index_result = self.backend.upsert_chunks(chunks) if self.backend is not None else {"indexed": 0, "backend": "none"}
        return {"documents_ingested": len(results), "chunks_created": len(chunks), "index": index_result, "results": results}

    def ingest_json_file(self, path: str | Path, actor: str = "bootstrap"):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        docs = raw if isinstance(raw, list) else raw.get("documents", [])
        return self.ingest_documents(docs, actor=actor)
