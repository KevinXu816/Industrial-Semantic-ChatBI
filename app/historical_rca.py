"""Historical confirmed RCA cases as governed reusable knowledge."""
from __future__ import annotations
import math
import re
from typing import Any, Dict, List
from .persistence import Repository


def _terms(text: str):
    latin = re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())
    chinese = [c for c in (text or "") if "\u4e00" <= c <= "\u9fff"]
    return set(latin + chinese)


class HistoricalRCARetriever:
    def __init__(self, repository: Repository):
        self.repo = repository

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        q = _terms(query)
        out = []
        for case in self.repo.list("rca_cases", limit=1000):
            if case.get("status") not in {"reviewed", "resolved", "closed"}:
                continue
            cause = case.get("confirmed_root_cause")
            if not cause:
                continue
            resolution = case.get("resolution") or {}
            text = " ".join([str(case.get("title", "")), str(case.get("question", "")), str(cause), str(resolution.get("action", "")), str(resolution.get("comment", ""))])
            d = _terms(text)
            overlap = len(q & d)
            if not overlap:
                continue
            score = overlap / max(1.0, math.sqrt(max(1, len(q)) * max(1, len(d))))
            case_id = str(case.get("case_id"))
            out.append({
                "id": case_id,
                "document_id": case_id,
                "type": "HistoricalRCA",
                "title": case.get("title") or case_id,
                "content": case.get("question", ""),
                "failure_mode": cause,
                "confirmed_root_cause": cause,
                "action": resolution.get("action"),
                "resolution": resolution,
                "subject": case.get("subject"),
                "tags": [str(cause), "historical_rca"],
                "retrieval_score": round(score, 4),
                "citation": f"RCA:{case_id}",
                "provenance": f"rca_case:{case_id}",
                "retrieval_backend": "historical_rca",
            })
        out.sort(key=lambda x: x["retrieval_score"], reverse=True)
        return out[:max(1, min(int(top_k), 20))]
