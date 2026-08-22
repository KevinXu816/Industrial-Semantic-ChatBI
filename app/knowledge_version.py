"""Knowledge document versioning and citation helpers."""
from __future__ import annotations
import hashlib, json
from typing import Any, Dict, Iterable


def enrich_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    clean = dict(doc)
    version = str(clean.get("version") or "1.0")
    body = json.dumps({k: clean.get(k) for k in sorted(clean) if k not in {"retrieval_score", "provenance", "citation"}}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    doc_id = str(clean.get("id", "unknown"))
    clean["version"] = version; clean["knowledge_digest"] = digest
    clean["citation"] = f"{doc_id}@{version}#{digest}"
    clean["provenance"] = f"knowledge:{doc_id}:{version}:{digest}"
    return clean
