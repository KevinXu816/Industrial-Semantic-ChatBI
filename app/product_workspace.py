"""V2.0 productization aggregation for role-aware reliability workspaces."""
from __future__ import annotations
from typing import Any, Dict, List


class ProductWorkspaceService:
    def __init__(self, asset_cockpit, rca_store, cmms_store):
        self.asset_cockpit = asset_cockpit
        self.rca_store = rca_store
        self.cmms_store = cmms_store

    def home(self, role: str = "reliability_engineer", limit: int = 12) -> Dict[str, Any]:
        role = (role or "reliability_engineer").strip().lower()
        fleet = self.asset_cockpit.fleet(limit=500)
        assets = fleet.get("assets", [])
        critical = [a for a in assets if a.get("health_class") == "critical" or float(a.get("dynamic_risk") or 0) >= 80]
        open_rca = [x for x in self.rca_store.list(limit=500) if x.get("status") not in {"resolved", "closed"}]
        pending_wo = [x for x in self.cmms_store.list(limit=1000) if x.get("status") in {"draft", "approved"}]
        if role in {"maintenance_planner", "maintenance"}:
            priorities = [{"kind":"work_order","asset":x.get("asset"),"title":x.get("recommended_action") or x.get("description") or x.get("candidate_id"),"priority":x.get("priority"),"id":x.get("candidate_id")} for x in pending_wo]
        elif role in {"operator", "operations"}:
            priorities = [{"kind":"asset","asset":x.get("asset_id"),"title":x.get("name") or x.get("asset_id"),"priority":x.get("maintenance_priority"),"risk":x.get("dynamic_risk")} for x in assets if x.get("risk_trend") == "deteriorating"]
        else:
            priorities = [{"kind":"asset","asset":x.get("asset_id"),"title":x.get("name") or x.get("asset_id"),"priority":x.get("maintenance_priority"),"risk":x.get("dynamic_risk")} for x in critical]
            priorities += [{"kind":"rca","asset":(x.get("subject") or {}).get("reference"),"title":x.get("title"),"priority":"investigate","id":x.get("case_id")} for x in open_rca]
        return {
            "role": role,
            "summary": {
                "assets": fleet.get("total", len(assets)),
                "critical_assets": len(critical),
                "deteriorating_assets": sum(1 for a in assets if a.get("risk_trend") == "deteriorating"),
                "open_rca_cases": len(open_rca),
                "pending_work_orders": len(pending_wo),
            },
            "priorities": priorities[:limit],
            "fleet": assets[:limit],
            "semantics": "Role-aware workspace is an aggregation view over governed reliability/RCA/CMMS sources; it does not duplicate operational facts.",
        }
