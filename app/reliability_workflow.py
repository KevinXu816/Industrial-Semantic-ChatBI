"""V2.1 product workflow aggregation for RCA case review and maintenance closure.

This module is intentionally an application/view layer. It aggregates existing RCA, CMMS and
asset sources of truth and does not duplicate their operational state.
"""
from __future__ import annotations
from typing import Any, Dict, List


class RCAWorkflowService:
    STAGES = ("open", "analyzed", "reviewed", "resolved", "closed")

    def __init__(self, case_store, cmms_store, asset_registry):
        self.cases = case_store
        self.cmms = cmms_store
        self.assets = asset_registry

    def _asset_id(self, case: Dict[str, Any]) -> str:
        return str((case.get("subject") or {}).get("reference") or "")

    def _maintenance(self, asset_id: str) -> List[Dict[str, Any]]:
        if not asset_id:
            return []
        return [x for x in self.cmms.list(limit=1000) if str(x.get("asset") or "") == asset_id]

    def _evidence(self, case: Dict[str, Any]) -> List[Dict[str, Any]]:
        analysis = case.get("analysis") or {}
        rows: List[Dict[str, Any]] = []
        for h in analysis.get("hypotheses") or case.get("hypotheses") or []:
            code = h.get("cause_code") or h.get("cause") or "hypothesis"
            for ev in h.get("evidence") or []:
                if isinstance(ev, dict):
                    rows.append({"hypothesis": code, **ev})
                else:
                    rows.append({"hypothesis": code, "statement": str(ev), "type": "evidence"})
        graph = case.get("evidence_graph") or {}
        for node in graph.get("nodes") or []:
            if str(node.get("type") or "").lower() in {"evidence", "knowledge", "event", "sensorcorrelation"}:
                rows.append({
                    "type": node.get("type"),
                    "statement": node.get("label") or node.get("statement") or node.get("id"),
                    "provenance": node.get("provenance"),
                })
        # Stable, de-duplicated presentation list.
        seen = set(); out = []
        for row in rows:
            key = (str(row.get("type")), str(row.get("statement")), str(row.get("provenance")))
            if key in seen:
                continue
            seen.add(key); out.append(row)
        return out[:200]

    def get(self, case_id: str) -> Dict[str, Any]:
        case = self.cases.get(case_id)
        if not case:
            raise KeyError(case_id)
        asset_id = self._asset_id(case)
        status = str(case.get("status") or "open")
        current_index = self.STAGES.index(status) if status in self.STAGES else 0
        stages = []
        for i, stage in enumerate(self.STAGES):
            stages.append({
                "stage": stage,
                "state": "done" if i < current_index else ("current" if i == current_index else "pending"),
            })
        hypotheses = case.get("hypotheses") or ((case.get("analysis") or {}).get("hypotheses") or [])
        return {
            "case": case,
            "asset": self.assets.get_asset(asset_id) if asset_id else None,
            "workflow": stages,
            "hypotheses": hypotheses,
            "evidence": self._evidence(case),
            "maintenance": self._maintenance(asset_id),
            "actions": {
                "can_analyze": status == "open",
                "can_review": status == "analyzed",
                "can_resolve": status in {"analyzed", "reviewed"},
                "can_close": status == "resolved",
            },
            "semantics": "RCA workflow is an aggregation view; case, evidence and maintenance facts remain in their governed domain stores.",
        }

    def list(self, status: str = "", asset: str = "", limit: int = 100) -> Dict[str, Any]:
        rows = self.cases.list(limit=500, status=status or None)
        if asset:
            rows = [r for r in rows if self._asset_id(r) == asset]
        items = []
        for row in rows[:limit]:
            aid = self._asset_id(row)
            hyps = row.get("hypotheses") or ((row.get("analysis") or {}).get("hypotheses") or [])
            top = hyps[0] if hyps else {}
            items.append({
                "case_id": row.get("case_id"), "status": row.get("status"), "title": row.get("title"),
                "asset": aid, "updated_at": row.get("updated_at"),
                "top_hypothesis": top.get("cause") or top.get("cause_code"),
                "confidence": top.get("confidence"),
                "confirmed_root_cause": row.get("confirmed_root_cause"),
            })
        return {"cases": items, "total": len(items)}
