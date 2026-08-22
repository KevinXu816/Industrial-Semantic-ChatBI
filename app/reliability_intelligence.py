"""V1.5 reliability intelligence and predictive-maintenance decision support.

The module intentionally produces explainable *risk indicators*, not failure-probability
claims. Scores combine approved FMEA risk with governed condition, anomaly and history
signals and preserve the contribution of every factor.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
from .persistence import Repository
from .fmea import FMEAStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _indicator_score(item: Dict[str, Any]) -> float:
    """Normalize a condition indicator to 0..100.

    Accepted inputs:
    - score: already-normalized 0..100
    - value/baseline/tolerance: deviation relative to allowed tolerance
    - value/warn/critical: threshold interpolation
    """
    if item.get("score") is not None:
        return _clamp(float(item["score"]))
    value = float(item.get("value", 0.0))
    if item.get("baseline") is not None:
        baseline = float(item.get("baseline") or 0.0)
        tolerance = abs(float(item.get("tolerance", 0.0)))
        if tolerance <= 0:
            tolerance = max(abs(baseline) * 0.10, 1e-9)
        return _clamp(abs(value - baseline) / tolerance * 50.0)
    if item.get("warn") is not None and item.get("critical") is not None:
        warn, critical = float(item["warn"]), float(item["critical"])
        direction = str(item.get("direction", "high")).lower()
        if direction == "low":
            if value >= warn: return 0.0
            if value <= critical: return 100.0
            return _clamp((warn - value) / max(warn - critical, 1e-9) * 100.0)
        if value <= warn: return 0.0
        if value >= critical: return 100.0
        return _clamp((value - warn) / max(critical - warn, 1e-9) * 100.0)
    return 0.0


class FailureSensorMappingStore:
    COLLECTION = "failure_sensor_mappings"
    def __init__(self, repository: Repository): self.repo = repository
    def upsert(self, payload: Dict[str, Any], actor: str = "reliability_engineer") -> Dict[str, Any]:
        fm = str(payload.get("failure_mode") or payload.get("cause_code") or "").strip()
        sensor = str(payload.get("sensor") or payload.get("indicator") or "").strip()
        if not fm or not sensor: raise ValueError("failure_mode and sensor are required")
        key = str(payload.get("mapping_id") or hashlib.sha1(f"{fm}:{sensor}".encode()).hexdigest()[:16])
        row = dict(payload); row.update({"mapping_id": key, "failure_mode": fm, "sensor": sensor, "updated_at": _now(), "updated_by": actor})
        row.setdefault("weight", 1.0); row.setdefault("status", "approved")
        return self.repo.put(self.COLLECTION, key, row)
    def list(self, failure_mode: str = "", status: str = "approved", limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.COLLECTION, limit=min(max(limit * 3, 200), 1000))
        return [r for r in rows if (not failure_mode or r.get("failure_mode") == failure_mode) and (not status or r.get("status") == status)][:limit]


class ReliabilityIntelligenceService:
    COLLECTION = "reliability_assessments"
    def __init__(self, repository: Repository, fmea_store: FMEAStore, mappings: FailureSensorMappingStore):
        self.repo, self.fmea, self.mappings = repository, fmea_store, mappings

    @staticmethod
    def _static_score(fmea: Dict[str, Any]) -> float:
        # Preserve severity dominance while normalizing the 1..1000 RPN space.
        rpn = float(fmea.get("rpn", 0))
        severity = float(fmea.get("severity", 1))
        return round(_clamp(0.60 * (rpn / 10.0) + 0.40 * (severity * 10.0)), 2)

    def assess_failure_mode(self, fmea: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        indicators = list(payload.get("condition_indicators") or [])
        indicator_details = []
        weighted_sum = weight_sum = 0.0
        known = {m.get("sensor"): m for m in self.mappings.list(str(fmea.get("cause_code") or fmea.get("failure_mode")), status="approved")}
        for item in indicators:
            name = str(item.get("sensor") or item.get("name") or "indicator")
            score = _indicator_score(item)
            weight = float(item.get("weight", known.get(name, {}).get("weight", 1.0)) or 1.0)
            weighted_sum += score * max(weight, 0.0); weight_sum += max(weight, 0.0)
            indicator_details.append({**item, "sensor": name, "risk_score": round(score, 2), "weight": weight, "mapped": name in known})
        condition_score = weighted_sum / weight_sum if weight_sum else float(payload.get("condition_score", 0.0) or 0.0)
        anomaly_score = _clamp(float(payload.get("anomaly_score", 0.0) or 0.0))
        history_score = _clamp(float(payload.get("failure_history_score", payload.get("history_score", 0.0)) or 0.0))
        static_score = self._static_score(fmea)
        dynamic = _clamp(0.40 * static_score + 0.30 * condition_score + 0.15 * anomaly_score + 0.15 * history_score)
        if dynamic >= 80: priority, rec = "P1-critical", "Inspect immediately and create a maintenance work order."
        elif dynamic >= 65: priority, rec = "P2-high", "Schedule inspection in the next maintenance window."
        elif dynamic >= 45: priority, rec = "P3-medium", "Increase monitoring frequency and verify mapped condition indicators."
        else: priority, rec = "P4-low", "Continue routine monitoring."
        return {
            "fmea_id": fmea.get("fmea_id"), "asset": fmea.get("asset"), "component": fmea.get("component"),
            "failure_mode": fmea.get("failure_mode"), "cause_code": fmea.get("cause_code") or fmea.get("failure_mode"),
            "fmea_rpn": fmea.get("rpn"), "criticality": fmea.get("criticality"),
            "static_fmea_score": round(static_score, 2), "condition_risk_score": round(condition_score, 2),
            "anomaly_risk_score": round(anomaly_score, 2), "failure_history_score": round(history_score, 2),
            "dynamic_risk_score": round(dynamic, 2), "maintenance_priority": priority,
            "inspection_recommendation": rec, "condition_indicators": indicator_details,
            "explanation": {"weights": {"static_fmea": 0.40, "condition": 0.30, "anomaly": 0.15, "failure_history": 0.15}},
        }

    def assess(self, payload: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
        asset = str(payload.get("asset") or "").strip()
        approved = self.fmea.list(limit=1000, status="approved", asset=asset)
        requested = str(payload.get("failure_mode") or "").strip()
        if requested:
            approved = [r for r in approved if requested in {str(r.get("failure_mode")), str(r.get("cause_code"))}]
        if not approved: raise ValueError("no approved FMEA records match the requested asset/failure_mode")
        per_mode = payload.get("failure_modes") or {}
        results=[]
        for row in approved:
            key = str(row.get("cause_code") or row.get("failure_mode"))
            mode_payload = dict(payload); mode_payload.update(per_mode.get(key) or {})
            results.append(self.assess_failure_mode(row, mode_payload))
        results.sort(key=lambda r:r["dynamic_risk_score"], reverse=True)
        health = round(_clamp(100.0 - (results[0]["dynamic_risk_score"] if results else 0.0)), 2)
        if health >= 80: health_class="healthy"
        elif health >= 60: health_class="watch"
        elif health >= 40: health_class="degraded"
        else: health_class="critical"
        assessment_id = "REL-" + hashlib.sha1(f"{asset}:{_now()}".encode()).hexdigest()[:12].upper()
        out={"assessment_id":assessment_id,"asset":asset,"asset_health_score":health,"health_class":health_class,
             "failure_modes":results,"top_risk":results[0] if results else None,"created_at":_now(),"created_by":actor,
             "semantics":"Risk/health indicators are decision-support scores, not calibrated failure probabilities."}
        self.repo.put(self.COLLECTION,assessment_id,out); return out

    def history(self, asset: str, limit: int = 100) -> List[Dict[str, Any]]:
        return [r for r in self.repo.list(self.COLLECTION,limit=1000) if r.get("asset")==asset][:limit]

    def asset_health(self, asset: str, limit: int = 30) -> Dict[str, Any]:
        rows=self.history(asset,limit=limit)
        if not rows: return {"asset":asset,"assessments":0,"latest":None,"trend":"unknown"}
        latest=rows[0]; scores=[float(r.get("asset_health_score",0)) for r in rows]
        trend="stable"
        if len(scores)>=2:
            delta=scores[0]-scores[-1]
            if delta <= -5: trend="deteriorating"
            elif delta >= 5: trend="improving"
        return {"asset":asset,"assessments":len(rows),"latest":latest,"health_trend":trend,"health_scores":scores}

    def risk_ranking(self, limit: int = 20) -> List[Dict[str, Any]]:
        latest_by_asset={}
        for r in self.repo.list(self.COLLECTION,limit=1000):
            a=r.get("asset")
            if a and a not in latest_by_asset: latest_by_asset[a]=r
        rows=list(latest_by_asset.values()); rows.sort(key=lambda r: float((r.get("top_risk") or {}).get("dynamic_risk_score",0)),reverse=True)
        return rows[:limit]
