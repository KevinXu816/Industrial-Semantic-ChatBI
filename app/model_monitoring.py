"""V1.8 model evaluation, champion/challenger lifecycle and production monitoring."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib, math, statistics
from .persistence import Repository


def _now(): return datetime.now(timezone.utc).isoformat()
def _mean(xs): return sum(xs)/len(xs) if xs else 0.0
def _rmse(y, p): return math.sqrt(_mean([(a-b)**2 for a,b in zip(y,p)])) if y else 0.0
def _mae(y, p): return _mean([abs(a-b) for a,b in zip(y,p)]) if y else 0.0

def _binary_metrics(y: List[int], p: List[int]) -> Dict[str,float]:
    tp=sum(1 for a,b in zip(y,p) if a==1 and b==1); tn=sum(1 for a,b in zip(y,p) if a==0 and b==0)
    fp=sum(1 for a,b in zip(y,p) if a==0 and b==1); fn=sum(1 for a,b in zip(y,p) if a==1 and b==0)
    precision=tp/(tp+fp) if tp+fp else 0.0; recall=tp/(tp+fn) if tp+fn else 0.0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {"precision":round(precision,4),"recall":round(recall,4),"f1":round(f1,4),"false_alarm_rate":round(fp/(fp+tn),4) if fp+tn else 0.0,"miss_rate":round(fn/(fn+tp),4) if fn+tp else 0.0}

class ModelDatasetRegistry:
    COLLECTION="model_datasets"
    def __init__(self,repo:Repository): self.repo=repo
    def register(self,payload:Dict[str,Any],actor="ml_engineer"):
        name=str(payload.get("name") or "").strip(); version=str(payload.get("version") or "1.0")
        if not name: raise ValueError("dataset name is required")
        did=str(payload.get("dataset_id") or hashlib.sha1(f"{name}:{version}".encode()).hexdigest()[:18])
        row=dict(payload); row.update({"dataset_id":did,"name":name,"version":version,"updated_at":_now(),"updated_by":actor}); row.setdefault("status","approved"); row.setdefault("task","regression"); row.setdefault("records",[])
        return self.repo.put(self.COLLECTION,did,row)
    def get(self,did): return self.repo.get(self.COLLECTION,did)
    def list(self,status="",limit=200):
        rows=self.repo.list(self.COLLECTION,limit=limit); return [r for r in rows if not status or r.get("status")==status]

class ModelEvaluationService:
    COLLECTION="model_evaluations"
    def __init__(self,repo:Repository,model_registry,datasets:ModelDatasetRegistry): self.repo=repo; self.models=model_registry; self.datasets=datasets
    def evaluate(self,model_id:str,dataset_id:str,actor="ml_validator"):
        model=self.models.get(model_id); data=self.datasets.get(dataset_id)
        if not model: raise KeyError(f"model:{model_id}")
        if not data: raise KeyError(f"dataset:{dataset_id}")
        records=data.get("records") or []; task=str(data.get("task") or "regression")
        y=[]; pred=[]; skipped=0
        for rec in records:
            expected=rec.get("expected")
            try:
                result=self.models.infer(model_id,{"inputs":rec.get("inputs") or {}},actor="offline_evaluation", allow_candidate=True)["inference"]["output"]
                val=result.get("prediction", result.get("risk_score"))
                if expected is None or val is None: skipped+=1; continue
                y.append(float(expected)); pred.append(float(val))
            except Exception:
                skipped+=1
        metrics={"samples":len(y),"skipped":skipped}
        if task in {"classification","binary_classification"}:
            metrics.update(_binary_metrics([int(x) for x in y],[1 if x>=0.5 else 0 for x in pred]))
        else:
            metrics.update({"mae":round(_mae(y,pred),6),"rmse":round(_rmse(y,pred),6)})
            if task=="rul": metrics["rul_mae"]=metrics["mae"]
        eid="MEV-"+hashlib.sha1(f"{model_id}:{dataset_id}:{_now()}".encode()).hexdigest()[:16]
        row={"evaluation_id":eid,"model_id":model_id,"model_version":model.get("version"),"dataset_id":dataset_id,"dataset_version":data.get("version"),"task":task,"metrics":metrics,"created_at":_now(),"created_by":actor}
        return self.repo.put(self.COLLECTION,eid,row)
    def list(self,model_id="",limit=200):
        rows=self.repo.list(self.COLLECTION,limit=limit); return [r for r in rows if not model_id or r.get("model_id")==model_id]

class ModelDeploymentManager:
    COLLECTION="model_deployments"
    def __init__(self,repo:Repository,model_registry): self.repo=repo; self.models=model_registry
    def set_role(self,slot:str,model_id:str,role:str,actor="model_approver"):
        role=str(role).lower()
        if role not in {"champion","challenger"}: raise ValueError("role must be champion or challenger")
        m=self.models.get(model_id)
        if not m: raise KeyError(model_id)
        if m.get("status")!="approved": raise ValueError("only approved models can be deployed")
        row=self.repo.get(self.COLLECTION,slot) or {"slot":slot,"history":[]}
        prev=row.get(role)
        row[role]=model_id; row["updated_at"]=_now(); row["updated_by"]=actor
        row.setdefault("history",[]).append({"action":"set_role","role":role,"from":prev,"to":model_id,"at":_now(),"actor":actor})
        row["history"]=row["history"][-100:]
        return self.repo.put(self.COLLECTION,slot,row)
    def promote(self,slot:str,actor="model_approver"):
        row=self.repo.get(self.COLLECTION,slot)
        if not row or not row.get("challenger"): raise ValueError("challenger is not configured")
        old=row.get("champion"); new=row.get("challenger"); row["champion"]=new; row["challenger"]=old; row["updated_at"]=_now(); row["updated_by"]=actor
        row.setdefault("history",[]).append({"action":"promote","from":old,"to":new,"at":_now(),"actor":actor})
        return self.repo.put(self.COLLECTION,slot,row)
    def rollback(self,slot:str,actor="model_approver"):
        row=self.repo.get(self.COLLECTION,slot)
        if not row or not row.get("challenger"): raise ValueError("no rollback model available")
        old=row.get("champion"); new=row.get("challenger"); row["champion"]=new; row["challenger"]=old; row["updated_at"]=_now(); row["updated_by"]=actor
        row.setdefault("history",[]).append({"action":"rollback","from":old,"to":new,"at":_now(),"actor":actor})
        return self.repo.put(self.COLLECTION,slot,row)
    def get(self,slot): return self.repo.get(self.COLLECTION,slot)
    def list(self,limit=100): return self.repo.list(self.COLLECTION,limit=limit)

class ModelMonitoringService:
    BASELINES="model_monitoring_baselines"; EVENTS="model_monitoring_events"
    def __init__(self,repo:Repository): self.repo=repo
    def set_baseline(self,model_id:str,feature_stats:Dict[str,Any],actor="ml_engineer"):
        row={"model_id":model_id,"feature_stats":feature_stats,"updated_at":_now(),"updated_by":actor}
        return self.repo.put(self.BASELINES,model_id,row)
    @staticmethod
    def _drift(base:Dict[str,Any],cur:Dict[str,Any]):
        out={}
        for feature,b in base.items():
            c=cur.get(feature) or {}; bm=float((b or {}).get("mean",0)); bs=abs(float((b or {}).get("std",0))) or 1e-9; cm=float(c.get("mean",bm))
            z=abs(cm-bm)/bs; out[feature]={"mean_shift_sigma":round(z,4),"status":"drift" if z>=3 else ("watch" if z>=2 else "stable")}
        return out
    def monitor(self,model_id:str,current_feature_stats:Dict[str,Any],performance:Optional[Dict[str,Any]]=None,actor="monitor"):
        baseline=self.repo.get(self.BASELINES,model_id) or {"feature_stats":{}}
        drift=self._drift(baseline.get("feature_stats") or {},current_feature_stats or {})
        worst=max([v["mean_shift_sigma"] for v in drift.values()] or [0]); status="drift" if worst>=3 else ("watch" if worst>=2 else "stable")
        eid="MME-"+hashlib.sha1(f"{model_id}:{_now()}".encode()).hexdigest()[:16]
        row={"event_id":eid,"model_id":model_id,"status":status,"feature_drift":drift,"performance":performance or {},"created_at":_now(),"created_by":actor}
        return self.repo.put(self.EVENTS,eid,row)
    def recent(self,model_id="",limit=100):
        rows=self.repo.list(self.EVENTS,limit=limit); return [r for r in rows if not model_id or r.get("model_id")==model_id]
    def summary(self):
        rows=self.repo.list(self.EVENTS,limit=1000); return {"events":len(rows),"drift":sum(1 for r in rows if r.get("status")=="drift"),"watch":sum(1 for r in rows if r.get("status")=="watch")}
