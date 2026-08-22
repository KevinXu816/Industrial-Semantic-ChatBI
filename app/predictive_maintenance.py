"""V1.6 predictive-maintenance adapters and CMMS work-order contract.

RUL values are trend-based engineering estimates unless a calibrated external RUL model is
plugged in. The module intentionally labels this uncertainty in every response.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib

from .persistence import Repository


def _now() -> str: return datetime.now(timezone.utc).isoformat()


class RULAdapter:
    name = "abstract"
    def estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]: raise NotImplementedError


class TrendRULAdapter(RULAdapter):
    name = "linear_health_trend"
    def estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        values=[]
        for x in payload.get("health_scores") or []:
            try: values.append(float(x))
            except (TypeError,ValueError): pass
        threshold=float(payload.get("failure_threshold",20.0) or 20.0)
        interval_hours=float(payload.get("interval_hours",24.0) or 24.0)
        if len(values) < 2:
            return {"adapter":self.name,"status":"insufficient_data","estimated_rul_hours":None,
                    "semantics":"RUL is unavailable until at least two health observations exist."}
        # Input is expected oldest -> newest for the adapter contract.
        n=len(values); xm=(n-1)/2.0; ym=sum(values)/n
        denom=sum((i-xm)**2 for i in range(n))
        slope=0.0 if not denom else sum((i-xm)*(y-ym) for i,y in enumerate(values))/denom
        current=values[-1]
        if slope >= -1e-9 or current <= threshold:
            rul = 0.0 if current <= threshold else None
        else:
            rul=max(0.0,(threshold-current)/slope*interval_hours)
        return {"adapter":self.name,"status":"ok","current_health":round(current,2),"trend_per_interval":round(slope,4),
                "failure_threshold":threshold,"interval_hours":interval_hours,
                "estimated_rul_hours":None if rul is None else round(rul,2),
                "semantics":"Trend-based engineering estimate; not a calibrated failure-time probability."}


class MaintenanceDecisionService:
    def recommend(self, reliability: Dict[str, Any], rul: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        top=reliability.get("top_risk") or {}
        risk=float(top.get("dynamic_risk_score",0.0) or 0.0)
        priority=str(top.get("maintenance_priority") or "P4-low")
        rul_hours=(rul or {}).get("estimated_rul_hours")
        if rul_hours is not None and rul_hours <= 24: priority="P1-critical"
        elif rul_hours is not None and rul_hours <= 168 and priority not in {"P1-critical"}: priority="P2-high"
        if priority=="P1-critical": action="Create an urgent inspection/work-order candidate and verify the affected component immediately."
        elif priority=="P2-high": action="Schedule inspection in the next maintenance window and prepare the required work order/spares."
        elif priority=="P3-medium": action="Increase condition-monitoring frequency and inspect at the next planned service."
        else: action="Continue routine monitoring under the current maintenance plan."
        return {"asset":reliability.get("asset"),"priority":priority,"dynamic_risk_score":risk,
                "failure_mode":top.get("failure_mode"),"component":top.get("component"),"recommended_action":action,
                "estimated_rul_hours":rul_hours,"generated_at":_now(),
                "semantics":"Maintenance decision support; human approval is required before dispatching work."}


class CMMSWorkOrderCandidateStore:
    COLLECTION="cmms_work_order_candidates"
    VALID_STATUS={"draft","approved","dispatched","cancelled"}
    def __init__(self,repository:Repository): self.repo=repository
    def create(self,payload:Dict[str,Any],actor:str="system") -> Dict[str,Any]:
        asset=str(payload.get("asset") or "").strip()
        if not asset: raise ValueError("asset is required")
        key=str(payload.get("candidate_id") or "WO-CAND-"+hashlib.sha1(f"{asset}:{_now()}".encode()).hexdigest()[:12].upper())
        row=dict(payload); row.update({"candidate_id":key,"status":"draft","created_at":_now(),"created_by":actor,"updated_at":_now()})
        row.setdefault("history",[]); row["history"].append({"at":_now(),"action":"created","actor":actor})
        return self.repo.put(self.COLLECTION,key,row)
    def get(self,key:str): return self.repo.get(self.COLLECTION,key)
    def list(self,status:str="",limit:int=200):
        rows=self.repo.list(self.COLLECTION,limit=min(max(limit*3,200),1000))
        return [r for r in rows if not status or r.get("status")==status][:limit]
    def transition(self,key:str,status:str,actor:str="maintenance_planner",external_id:str=""):
        row=self.get(key)
        if not row: raise KeyError(key)
        if status not in self.VALID_STATUS: raise ValueError(f"unsupported CMMS candidate status: {status}")
        row["status"]=status; row["updated_at"]=_now(); row.setdefault("history",[]).append({"at":_now(),"action":status,"actor":actor})
        if external_id: row["external_work_order_id"]=external_id
        return self.repo.put(self.COLLECTION,key,row)

    @staticmethod
    def integration_contract(candidate:Dict[str,Any]) -> Dict[str,Any]:
        return {"contract_version":"1.0","operation":"create_work_order","payload":{
            "asset":candidate.get("asset"),"component":candidate.get("component"),"failure_mode":candidate.get("failure_mode"),
            "priority":candidate.get("priority"),"description":candidate.get("recommended_action") or candidate.get("description"),
            "source":"industrial_semantic_reliability","source_reference":candidate.get("candidate_id")},
            "semantics":"Vendor-neutral CMMS integration contract; adapter-specific dispatch is intentionally separate."}
