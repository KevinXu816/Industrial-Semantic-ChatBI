"""Deterministic document chunking for governed industrial knowledge ingestion."""
from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, List


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def chunk_document(doc: Dict[str, Any], chunk_size: int = 420, overlap: int = 80) -> List[Dict[str, Any]]:
    """Split a knowledge document into stable character chunks.

    Stable chunk ids are derived from document id/version/content so citations can
    be reproduced across ingestion runs.
    """
    chunk_size = max(120, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size // 2))
    content = _normalize(str(doc.get("content") or ""))
    if not content:
        content = _normalize(" ".join(str(doc.get(k, "")) for k in ("title", "action", "failure_mode")))
    if not content:
        return []
    doc_id = str(doc.get("id") or doc.get("document_id") or "unknown")
    version = str(doc.get("version") or "1.0")
    chunks: List[Dict[str, Any]] = []
    start = 0
    idx = 0
    while start < len(content):
        end = min(len(content), start + chunk_size)
        if end < len(content):
            # Prefer a natural sentence boundary close to the target end.
            segment = content[start:end]
            cut = max(segment.rfind("。"), segment.rfind("；"), segment.rfind("."), segment.rfind(";"))
            if cut >= int(chunk_size * 0.55):
                end = start + cut + 1
        text = content[start:end].strip()
        if text:
            raw = f"{doc_id}|{version}|{idx}|{text}".encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()[:16]
            chunks.append({
                "chunk_id": f"{doc_id}:{version}:{idx}:{digest}",
                "document_id": doc_id,
                "version": version,
                "chunk_index": idx,
                "text": text,
                "title": doc.get("title", ""),
                "type": doc.get("type", "Document"),
                "failure_mode": doc.get("failure_mode"),
                "tags": doc.get("tags", []),
                "status": doc.get("status", "approved"),
                "knowledge_digest": doc.get("knowledge_digest"),
                "citation": doc.get("citation"),
                "provenance": doc.get("provenance"),
                "parent_citation": doc.get("citation"),
                "parent_provenance": doc.get("provenance"),
                "effective_from": doc.get("effective_from"),
                "effective_to": doc.get("effective_to"),
                "source_case_id": doc.get("source_case_id"),
            })
            idx += 1
        if end >= len(content):
            break
        start = max(start + 1, end - overlap)
    return chunks
