"""Governed hybrid knowledge retrieval for FMEA/SOP/manual and historical RCA evidence."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from .knowledge_version import enrich_document


class KnowledgeRetriever:
    """Compatibility local-file retriever used when no persistent knowledge service is injected."""
    def __init__(self, path: str | Path | None = None):
        root = Path(__file__).resolve().parents[1]
        self.path = Path(path) if path else root / "data" / "knowledge_base.json"
        self.documents = self._load()

    def _load(self):
        if not self.path.exists(): return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")); return raw if isinstance(raw,list) else raw.get("documents",[])
        except Exception: return []

    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None):
        from .knowledge_backends import _terms
        import math
        q=_terms(query); filters=filters or {}; out=[]
        for doc in self.documents:
            if any(str(doc.get(k))!=str(v) for k,v in filters.items() if v is not None): continue
            d=_terms(" ".join(str(doc.get(k,"")) for k in ("title","content","tags","failure_mode","action")))
            overlap=len(q&d)
            if not overlap: continue
            score=overlap/max(1.0,math.sqrt(max(1,len(q))*max(1,len(d))))
            out.append({**enrich_document(doc),"retrieval_score":round(score,4),"retrieval_backend":"local_file"})
        out.sort(key=lambda x:x["retrieval_score"],reverse=True); return out[:max(1,min(int(top_k),20))]


class HybridKnowledgeRetriever:
    def __init__(self, backend, historical_rca=None):
        self.backend = backend
        self.historical_rca = historical_rca

    def search(self, query: str, top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        primary = self.backend.search(query, top_k=max(top_k, 5), filters=filters)
        historical = []
        # Type filters for normal documents should not unexpectedly inject RCA cases.
        if self.historical_rca is not None and not (filters or {}).get("type"):
            historical = self.historical_rca.search(query, top_k=max(2, top_k // 2))
        merged = primary + historical
        merged.sort(key=lambda x: float(x.get("retrieval_score", 0)), reverse=True)
        return merged[:max(1, min(int(top_k), 50))]

    def health(self):
        result = self.backend.health()
        result["historical_rca"] = self.historical_rca is not None
        return result
