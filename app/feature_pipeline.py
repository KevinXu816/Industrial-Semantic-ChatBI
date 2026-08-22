"""V1.7 auditable feature-pipeline jobs over raw time series."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict
import hashlib
from .persistence import Repository


def _now(): return datetime.now(timezone.utc).isoformat()

class FeaturePipelineStore:
    COLLECTION="feature_pipeline_jobs"
    RUNS="feature_pipeline_runs"
    def __init__(self,repository:Repository): self.repo=repository
    def upsert(self,payload:Dict[str,Any],actor="data_engineer"):
        name=str(payload.get("name") or "").strip()
        if not name: raise ValueError("pipeline name is required")
        key=str(payload.get("pipeline_id") or hashlib.sha1(name.encode()).hexdigest()[:16])
        row=dict(payload); row.update({"pipeline_id":key,"name":name,"updated_at":_now(),"updated_by":actor}); row.setdefault("status","approved"); row.setdefault("source","payload")
        return self.repo.put(self.COLLECTION,key,row)
    def get(self,key): return self.repo.get(self.COLLECTION,key)
    def list(self,status="",limit=200):
        rows=self.repo.list(self.COLLECTION,limit=limit); return [r for r in rows if not status or r.get("status")==status]
    def execute(self,pipeline_id:str,payload:Dict[str,Any],condition_service,actor="system"):
        p=self.get(pipeline_id)
        if not p: raise KeyError(pipeline_id)
        analysis_payload={"asset":payload.get("asset"),"series":payload.get("series") or {},"definition_ids":p.get("definition_ids") or payload.get("definition_ids") or []}
        result=condition_service.analyze(analysis_payload)
        run_id="FPR-"+hashlib.sha1(f"{pipeline_id}:{_now()}".encode()).hexdigest()[:16]
        row={"run_id":run_id,"pipeline_id":pipeline_id,"asset":payload.get("asset"),"status":"succeeded","result":result,"executed_at":_now(),"executed_by":actor,
             "semantics":"On-demand execution contract. External schedulers may invoke this endpoint at governed intervals."}
        self.repo.put(self.RUNS,run_id,row); return row
    def runs(self,pipeline_id="",limit=100):
        rows=self.repo.list(self.RUNS,limit=limit); return [r for r in rows if not pipeline_id or r.get("pipeline_id")==pipeline_id]
