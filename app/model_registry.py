"""V1.7 governed predictive model registry and pluggable inference adapters."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import hashlib, math
from .persistence import Repository


def _now(): return datetime.now(timezone.utc).isoformat()

class PredictiveModelRegistry:
    COLLECTION="predictive_models"
    RUNS="model_inference_runs"
    VALID_TYPES={"rule","statistical","linear_rul","darts","onnx","external"}
    def __init__(self,repository:Repository): self.repo=repository
    def register(self,payload:Dict[str,Any],actor="ml_engineer"):
        name=str(payload.get("name") or "").strip(); typ=str(payload.get("model_type") or "rule").lower(); version=str(payload.get("version") or "1.0")
        if not name: raise ValueError("model name is required")
        if typ not in self.VALID_TYPES: raise ValueError(f"unsupported model_type: {typ}")
        mid=str(payload.get("model_id") or hashlib.sha1(f"{name}:{version}".encode()).hexdigest()[:18])
        row=dict(payload); row.update({"model_id":mid,"name":name,"model_type":typ,"version":version,"updated_at":_now(),"updated_by":actor}); row.setdefault("status","candidate"); row.setdefault("input_contract",{}); row.setdefault("output_contract",{})
        return self.repo.put(self.COLLECTION,mid,row)
    def get(self,mid): return self.repo.get(self.COLLECTION,mid)
    def list(self,status="",model_type="",limit=200):
        rows=self.repo.list(self.COLLECTION,limit=limit); return [r for r in rows if (not status or r.get("status")==status) and (not model_type or r.get("model_type")==model_type)]
    def approve(self,mid,actor="model_approver"):
        r=self.get(mid)
        if not r: raise KeyError(mid)
        r.update({"status":"approved","approved_at":_now(),"approved_by":actor}); return self.repo.put(self.COLLECTION,mid,r)
    def retire(self,mid,actor="model_approver"):
        r=self.get(mid)
        if not r: raise KeyError(mid)
        r.update({"status":"retired","retired_at":_now(),"retired_by":actor}); return self.repo.put(self.COLLECTION,mid,r)
    def infer(self,mid,payload:Dict[str,Any],actor="system", allow_candidate: bool = False):
        m=self.get(mid)
        if not m: raise KeyError(mid)
        if m.get("status")!="approved" and not allow_candidate: raise ValueError("only approved models may run inference")
        typ=m.get("model_type"); params=m.get("parameters") or {}; inputs=payload.get("inputs") or payload
        if typ=="rule":
            field=str(params.get("field") or "value"); x=float(inputs.get(field,0)); warn=float(params.get("warn",0)); critical=float(params.get("critical",100)); score=0.0 if x<=warn else (100.0 if x>=critical else (x-warn)/max(critical-warn,1e-9)*100)
            output={"risk_score":round(max(0,min(100,score)),2)}
        elif typ in {"statistical","linear_rul"}:
            vals=[float(x) for x in (inputs.get("values") or inputs.get("health_scores") or [])]
            if len(vals)<2: output={"status":"insufficient_data","prediction":None}
            else:
                n=len(vals); xm=(n-1)/2; ym=sum(vals)/n; den=sum((i-xm)**2 for i in range(n)); slope=sum((i-xm)*(y-ym) for i,y in enumerate(vals))/den if den else 0
                output={"trend_slope":round(slope,6),"prediction":round(vals[-1]+slope,6)}
        elif typ in {"darts","onnx","external"}:
            output={"status":"adapter_required","prediction":None,"adapter":typ,"artifact_uri":m.get("artifact_uri"),"message":"Register an enterprise inference adapter for this governed model type."}
        else: raise ValueError("unsupported model type")
        run_id="MIR-"+hashlib.sha1(f"{mid}:{_now()}".encode()).hexdigest()[:16]
        run={"run_id":run_id,"model_id":mid,"model_version":m.get("version"),"model_type":typ,"output":output,"executed_at":_now(),"executed_by":actor}
        self.repo.put(self.RUNS,run_id,run)
        return {"model":m,"inference":run}
