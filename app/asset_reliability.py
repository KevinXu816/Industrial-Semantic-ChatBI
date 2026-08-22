"""V1.9 asset registry and reliability cockpit aggregation.

The registry owns only asset master data, hierarchy, components and sensor bindings.
Operational health/risk/RCA/maintenance/model state is aggregated from existing services so
there is one source of truth for each domain fact.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import hashlib
from .persistence import Repository
from .enterprise_identity import default_tenant_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AssetRegistry:
    ASSETS = "asset_registry"
    COMPONENTS = "asset_components"
    SENSORS = "asset_sensor_bindings"

    def __init__(self, repo: Repository):
        self.repo = repo

    def upsert_asset(self, payload: Dict[str, Any], actor: str = "asset_engineer") -> Dict[str, Any]:
        asset_id = str(payload.get("asset_id") or payload.get("asset") or "").strip()
        if not asset_id:
            raise ValueError("asset_id is required")
        current = self.repo.get(self.ASSETS, asset_id) or {}
        row = {**current, **payload}
        row.update({"asset_id": asset_id, "updated_at": _now(), "updated_by": actor})
        row.setdefault("name", asset_id)
        row.setdefault("asset_type", "equipment")
        row.setdefault("status", "active")
        row.setdefault("parent_asset_id", "")
        row.setdefault("metadata", {})
        row.setdefault("tenant_id", default_tenant_id())
        row.setdefault("org_id", "")
        row.setdefault("site_id", "")
        row.setdefault("created_at", current.get("created_at") or _now())
        return self.repo.put(self.ASSETS, asset_id, row)

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get(self.ASSETS, asset_id)

    def list_assets(self, asset_type: str = "", status: str = "", parent_asset_id: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.ASSETS, limit=min(max(limit * 2, 500), 5000))
        if asset_type:
            rows = [r for r in rows if r.get("asset_type") == asset_type]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if parent_asset_id is not None:
            rows = [r for r in rows if str(r.get("parent_asset_id") or "") == str(parent_asset_id)]
        return rows[:limit]

    def hierarchy(self, root_asset_id: str = "") -> Dict[str, Any]:
        assets = self.list_assets(limit=5000)
        by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for row in assets:
            by_parent.setdefault(str(row.get("parent_asset_id") or ""), []).append(row)

        def build(asset: Dict[str, Any], seen: set) -> Dict[str, Any]:
            aid = str(asset.get("asset_id"))
            if aid in seen:
                return {**asset, "children": [], "cycle_detected": True}
            nxt = set(seen); nxt.add(aid)
            return {**asset, "children": [build(c, nxt) for c in by_parent.get(aid, [])]}

        if root_asset_id:
            root = self.get_asset(root_asset_id)
            if not root:
                raise KeyError(root_asset_id)
            return {"roots": [build(root, set())]}
        roots = [r for r in assets if not r.get("parent_asset_id") or not self.get_asset(str(r.get("parent_asset_id")))]
        return {"roots": [build(r, set()) for r in roots], "assets": len(assets)}

    def upsert_component(self, asset_id: str, payload: Dict[str, Any], actor: str = "asset_engineer") -> Dict[str, Any]:
        if not self.get_asset(asset_id):
            raise KeyError(asset_id)
        name = str(payload.get("name") or payload.get("component") or "").strip()
        if not name:
            raise ValueError("component name is required")
        component_id = str(payload.get("component_id") or hashlib.sha1(f"{asset_id}:{name}".encode()).hexdigest()[:18])
        current = self.repo.get(self.COMPONENTS, component_id) or {}
        row = {**current, **payload, "component_id": component_id, "asset_id": asset_id, "name": name,
               "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active"); row.setdefault("metadata", {}); row.setdefault("created_at", current.get("created_at") or _now())
        return self.repo.put(self.COMPONENTS, component_id, row)

    def components(self, asset_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        return [r for r in self.repo.list(self.COMPONENTS, limit=5000) if r.get("asset_id") == asset_id][:limit]

    def bind_sensor(self, asset_id: str, payload: Dict[str, Any], actor: str = "asset_engineer") -> Dict[str, Any]:
        if not self.get_asset(asset_id):
            raise KeyError(asset_id)
        sensor = str(payload.get("sensor") or payload.get("sensor_id") or "").strip()
        if not sensor:
            raise ValueError("sensor is required")
        component_id = str(payload.get("component_id") or "")
        if component_id:
            comp = self.repo.get(self.COMPONENTS, component_id)
            if not comp or comp.get("asset_id") != asset_id:
                raise ValueError("component_id does not belong to asset")
        binding_id = str(payload.get("binding_id") or hashlib.sha1(f"{asset_id}:{component_id}:{sensor}".encode()).hexdigest()[:18])
        current = self.repo.get(self.SENSORS, binding_id) or {}
        row = {**current, **payload, "binding_id": binding_id, "asset_id": asset_id, "sensor": sensor,
               "component_id": component_id, "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active"); row.setdefault("source", "IoT"); row.setdefault("unit", ""); row.setdefault("created_at", current.get("created_at") or _now())
        return self.repo.put(self.SENSORS, binding_id, row)

    def sensors(self, asset_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        return [r for r in self.repo.list(self.SENSORS, limit=5000) if r.get("asset_id") == asset_id][:limit]

    def stats(self) -> Dict[str, Any]:
        assets = self.repo.list(self.ASSETS, limit=5000)
        components = self.repo.list(self.COMPONENTS, limit=5000)
        sensors = self.repo.list(self.SENSORS, limit=5000)
        return {"assets": len(assets), "components": len(components), "sensor_bindings": len(sensors),
                "active_assets": sum(1 for a in assets if a.get("status") == "active")}


class AssetReliabilityCockpitService:
    def __init__(self, registry: AssetRegistry, reliability_service, fmea_store, rca_case_store,
                 cmms_candidates, model_deployments, model_registry, rul_adapter):
        self.registry = registry
        self.reliability = reliability_service
        self.fmea = fmea_store
        self.rca = rca_case_store
        self.cmms = cmms_candidates
        self.deployments = model_deployments
        self.models = model_registry
        self.rul_adapter = rul_adapter

    def _rca_cases(self, asset_id: str) -> List[Dict[str, Any]]:
        rows = self.rca.list(limit=500)
        return [r for r in rows if str((r.get("subject") or {}).get("reference") or "") == asset_id]

    def _work_orders(self, asset_id: str) -> List[Dict[str, Any]]:
        return [r for r in self.cmms.list(limit=1000) if str(r.get("asset") or "") == asset_id]

    def _models(self, asset_id: str, failure_modes: List[str]) -> List[Dict[str, Any]]:
        result=[]
        for dep in self.deployments.list(limit=500):
            slot = str(dep.get("slot") or "")
            related = (asset_id.lower() in slot.lower()) or any(fm and fm.lower() in slot.lower() for fm in failure_modes)
            if not related and failure_modes:
                continue
            row={"slot":slot,"champion":dep.get("champion"),"challenger":dep.get("challenger")}
            if dep.get("champion"):
                m=self.models.get(dep.get("champion")); row["champion_model"] = m
            if dep.get("challenger"):
                m=self.models.get(dep.get("challenger")); row["challenger_model"] = m
            result.append(row)
        return result

    def cockpit(self, asset_id: str, health_limit: int = 30, days: int = 30) -> Dict[str, Any]:
        asset = self.registry.get_asset(asset_id)
        if not asset:
            raise KeyError(asset_id)
        components = self.registry.components(asset_id)
        sensors = self.registry.sensors(asset_id)
        health = self.reliability.asset_health(asset_id, limit=health_limit)
        latest = health.get("latest") or {}
        top = latest.get("top_risk") or {}
        fmea = self.fmea.list(limit=1000, status="approved", asset=asset_id)
        rca_cases = self._rca_cases(asset_id)
        open_rca = [r for r in rca_cases if r.get("status") not in {"resolved", "closed"}]
        work_orders = self._work_orders(asset_id)
        pending_wo = [w for w in work_orders if w.get("status") in {"draft", "approved"}]
        # V2.1 time-window filtering is presentation-oriented; source reliability history remains unchanged.
        days = max(1, min(int(days or 30), 3650))
        raw_health_rows = self.reliability.history(asset_id, limit=max(health_limit, 1000))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        def in_window(row):
            raw = row.get("created_at")
            if not raw:
                return True
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt >= cutoff
            except Exception:
                return True
        health_rows = [r for r in raw_health_rows if in_window(r)][-max(1, health_limit):]
        chronological = sorted(health_rows, key=lambda r: str(r.get("created_at", "")))
        health_scores = [float(r.get("asset_health_score", 0.0)) for r in chronological]
        rul = self.rul_adapter.estimate({"health_scores": health_scores, "failure_threshold": 20.0, "interval_hours": 24.0}) if health_scores else self.rul_adapter.estimate({"health_scores": []})
        failure_modes = [str(x.get("cause_code") or x.get("failure_mode") or "") for x in fmea]
        models = self._models(asset_id, failure_modes)
        timeline=[]
        for r in chronological:
            timeline.append({"at": r.get("created_at"), "type": "health", "title": f"Asset health {r.get('asset_health_score')}", "detail": (r.get("top_risk") or {}).get("failure_mode"), "severity": (r.get("top_risk") or {}).get("maintenance_priority")})
        for r in rca_cases:
            timeline.append({"at": r.get("updated_at") or r.get("created_at"), "type": "rca", "title": r.get("title") or r.get("case_id"), "detail": r.get("status"), "id": r.get("case_id")})
        for w in work_orders:
            timeline.append({"at": w.get("updated_at") or w.get("created_at"), "type": "maintenance", "title": w.get("recommended_action") or w.get("description") or w.get("candidate_id"), "detail": w.get("status"), "id": w.get("candidate_id")})
        timeline.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
        failure_drilldown=[]
        latest_modes = {str(x.get("cause_code") or x.get("failure_mode")): x for x in (latest.get("failure_modes") or [])}
        for fm in fmea:
            code=str(fm.get("cause_code") or fm.get("failure_mode") or "")
            run=latest_modes.get(code,{})
            failure_drilldown.append({
                "failure_mode": fm.get("failure_mode"), "cause_code": code, "component": fm.get("component"),
                "rpn": fm.get("rpn"), "criticality": fm.get("criticality"), "cause": fm.get("cause"), "effect": fm.get("effect"),
                "detection_method": fm.get("detection_method"), "recommended_action": fm.get("recommended_action"),
                "dynamic_risk": run.get("dynamic_risk_score"), "maintenance_priority": run.get("maintenance_priority"),
                "condition_risk": run.get("condition_risk_score"), "anomaly_risk": run.get("anomaly_risk_score"),
            })
        failure_drilldown.sort(key=lambda x: float(x.get("dynamic_risk") or -1), reverse=True)
        return {
            "asset": asset,
            "hierarchy": {"parent_asset_id": asset.get("parent_asset_id") or "", "children": self.registry.list_assets(parent_asset_id=asset_id, limit=500)},
            "components": components,
            "sensors": sensors,
            "health": health,
            "current_health_score": latest.get("asset_health_score"),
            "health_class": latest.get("health_class"),
            "risk_trend": health.get("health_trend", "unknown"),
            "top_failure_mode": top,
            "approved_fmea": fmea,
            "rul": rul,
            "rca": {"open": open_rca, "all": rca_cases, "open_count": len(open_rca)},
            "maintenance": {"pending": pending_wo, "all": work_orders, "pending_count": len(pending_wo)},
            "models": models,
            "health_history": [{"at": r.get("created_at"), "score": r.get("asset_health_score"), "risk": (r.get("top_risk") or {}).get("dynamic_risk_score")} for r in chronological],
            "time_window_days": days,
            "timeline": timeline[:100],
            "failure_drilldown": failure_drilldown,
            "summary": {
                "components": len(components), "sensors": len(sensors), "approved_failure_modes": len(fmea),
                "open_rca_cases": len(open_rca), "pending_work_orders": len(pending_wo),
                "dynamic_risk": top.get("dynamic_risk_score"), "maintenance_priority": top.get("maintenance_priority"),
            },
            "semantics": "Cockpit aggregates governed domain sources; operational facts are not duplicated in the asset registry.",
        }

    def fleet(self, limit: int = 100) -> Dict[str, Any]:
        rows=[]
        for asset in self.registry.list_assets(status="active", limit=5000):
            aid=asset.get("asset_id")
            health=self.reliability.asset_health(aid, limit=30)
            latest=health.get("latest") or {}; top=latest.get("top_risk") or {}
            rows.append({"asset_id":aid,"name":asset.get("name"),"asset_type":asset.get("asset_type"),
                         "health_score":latest.get("asset_health_score"),"health_class":latest.get("health_class"),
                         "risk_trend":health.get("health_trend"),"top_failure_mode":top.get("failure_mode"),
                         "dynamic_risk":top.get("dynamic_risk_score"),"maintenance_priority":top.get("maintenance_priority"),
                         "open_rca_cases":len([x for x in self._rca_cases(aid) if x.get("status") not in {"resolved","closed"}]),
                         "pending_work_orders":len([x for x in self._work_orders(aid) if x.get("status") in {"draft","approved"}])})
        rows.sort(key=lambda r: (r.get("dynamic_risk") is not None, float(r.get("dynamic_risk") or -1)), reverse=True)
        return {"assets": rows[:limit], "total": len(rows)}
