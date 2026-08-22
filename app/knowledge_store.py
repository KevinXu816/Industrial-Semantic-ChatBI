"""Persistent knowledge document/chunk store over the V1.0 Repository contract."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .knowledge_chunking import chunk_document
from .knowledge_version import enrich_document
from .persistence import Repository


def _now():
    return datetime.now(timezone.utc).isoformat()


class KnowledgeStore:
    DOCS = "knowledge_documents"
    CHUNKS = "knowledge_chunks"

    def __init__(self, repository: Repository):
        self.repo = repository

    def put_document(self, document: Dict[str, Any], actor: str = "system", chunk_size: int = 420, overlap: int = 80):
        if not document.get("id") and not document.get("document_id"):
            raise ValueError("knowledge document requires id or document_id")
        doc = dict(document)
        doc["id"] = str(doc.get("id") or doc.get("document_id"))
        doc.setdefault("version", "1.0")
        doc.setdefault("status", "approved")
        doc.setdefault("created_at", _now())
        doc["updated_at"] = _now()
        doc["updated_by"] = actor
        doc = enrich_document(doc)
        key = f"{doc['id']}@{doc['version']}"
        self.repo.put(self.DOCS, key, doc)
        chunks = chunk_document(doc, chunk_size=chunk_size, overlap=overlap)
        for chunk in chunks:
            self.repo.put(self.CHUNKS, chunk["chunk_id"], chunk)
        return {"document": doc, "chunks": chunks, "chunk_count": len(chunks)}

    def replace_document(self, document: Dict[str, Any], actor: str = "system"):
        """Replace document metadata and rebuild chunk lineage deterministically."""
        doc = dict(document)
        doc["id"] = str(doc.get("id") or doc.get("document_id"))
        doc["updated_at"] = _now(); doc["updated_by"] = actor
        doc = enrich_document(doc)
        key = f"{doc['id']}@{doc.get('version','1.0')}"
        self.repo.put(self.DOCS, key, doc)
        chunks = chunk_document(doc)
        # Remove previous chunks for the same document/version before rebuilding.
        prefix = f"{doc['id']}:{doc.get('version','1.0')}:"
        for old in self.repo.list(self.CHUNKS, limit=10000):
            if str(old.get("chunk_id", "")).startswith(prefix):
                self.repo.delete(self.CHUNKS, old["chunk_id"])
        for chunk in chunks:
            self.repo.put(self.CHUNKS, chunk["chunk_id"], chunk)
        return {"document": doc, "chunks": chunks, "chunk_count": len(chunks)}

    def get_document(self, document_id: str, version: Optional[str] = None):
        if version:
            return self.repo.get(self.DOCS, f"{document_id}@{version}")
        rows = [x for x in self.repo.list(self.DOCS, limit=1000) if str(x.get("id")) == str(document_id)]
        rows.sort(key=lambda x: str(x.get("version", "")), reverse=True)
        return rows[0] if rows else None

    def list_documents(self, limit: int = 100, doc_type: str = "", status: str = ""):
        rows = self.repo.list(self.DOCS, limit=1000)
        if doc_type:
            rows = [r for r in rows if str(r.get("type", "")).lower() == doc_type.lower()]
        if status:
            rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
        return rows[:max(1, min(int(limit), 500))]

    def list_chunks(self, limit: int = 5000):
        return self.repo.list(self.CHUNKS, limit=max(1, min(int(limit), 10000)))

    def stats(self):
        docs = self.repo.list(self.DOCS, limit=1000)
        chunks = self.repo.list(self.CHUNKS, limit=10000)
        by_type = {}
        for d in docs:
            key = str(d.get("type", "Document"))
            by_type[key] = by_type.get(key, 0) + 1
        return {"documents": len(docs), "chunks": len(chunks), "by_type": by_type}
