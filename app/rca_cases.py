"""RCA Case Management for Enterprise Pilot lifecycle and review traceability."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .persistence import Repository
from .enterprise_identity import default_tenant_id

VALID_STATUS={"open","analyzed","reviewed","resolved","closed"}

def _now(): return datetime.now(timezone.utc).isoformat()

class RCACaseStore:
    COLLECTION="rca_cases"
    def __init__(self, repository: Repository): self.repo=repository
    def create(self,payload:Dict[str,Any],actor="anonymous"):
        now=_now(); case_id=payload.get("case_id") or f"RCA-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        record={"case_id":case_id,"status":"open","subject":payload.get("subject",{}),"title":payload.get("title") or payload.get("question") or case_id,
          "question":payload.get("question",""),"time_window":payload.get("time_window",{}),"metrics":payload.get("metrics",[]),
          "analysis":payload.get("analysis"),"evidence_graph":payload.get("evidence_graph"),"hypotheses":payload.get("hypotheses",[]),
          "confirmed_root_cause":None,"resolution":None,"review":None,"created_by":actor,"created_at":now,"updated_at":now,
          "tenant_id":payload.get("tenant_id") or default_tenant_id(),"org_id":payload.get("org_id") or "","site_id":payload.get("site_id") or "",
          "history":[{"at":now,"actor":actor,"action":"created","status":"open"}]}
        return self.repo.put(self.COLLECTION,case_id,record)
    def get(self,case_id): return self.repo.get(self.COLLECTION,case_id)
    def list(self,limit=100,status:Optional[str]=None):
        rows=self.repo.list(self.COLLECTION,limit=1000)
        if status: rows=[r for r in rows if r.get("status")==status]
        return rows[:max(1,min(int(limit),500))]
    def update(self,case_id,changes,actor="anonymous",action="updated"):
        rec=self.get(case_id)
        if not rec: raise KeyError(case_id)
        status=changes.get("status",rec.get("status"))
        if status not in VALID_STATUS: raise ValueError(f"Invalid RCA case status: {status}")
        protected={"case_id","created_at","created_by","history"}
        rec.update({k:v for k,v in changes.items() if k not in protected}); rec["updated_at"]=_now()
        rec.setdefault("history",[]).append({"at":rec["updated_at"],"actor":actor,"action":action,"status":status})
        return self.repo.put(self.COLLECTION,case_id,rec)
    def attach_analysis(self,case_id,analysis,evidence_graph=None,actor="system"):
        hypotheses=(analysis or {}).get("hypotheses",[]) if isinstance(analysis,dict) else []
        return self.update(case_id,{"analysis":analysis,"evidence_graph":evidence_graph,"hypotheses":hypotheses,"status":"analyzed"},actor,"analysis_attached")
    def review(self,case_id,payload,actor="engineer"):
        accepted=payload.get("accepted"); review={**payload,"reviewed_by":actor,"reviewed_at":_now()}
        changes={"review":review,"status":"reviewed"}
        if payload.get("correct_cause"): changes["confirmed_root_cause"]=payload["correct_cause"]
        elif accepted and payload.get("predicted_cause"): changes["confirmed_root_cause"]=payload["predicted_cause"]
        return self.update(case_id,changes,actor,"reviewed")
    def resolve(self,case_id,payload,actor="engineer"):
        changes={"status":"resolved","resolution":{**payload,"resolved_by":actor,"resolved_at":_now()}}
        if payload.get("confirmed_root_cause"): changes["confirmed_root_cause"]=payload["confirmed_root_cause"]
        return self.update(case_id,changes,actor,"resolved")
    def close(self,case_id,actor="engineer",comment=""):
        rec=self.get(case_id)
        if not rec: raise KeyError(case_id)
        if rec.get("status") != "resolved": raise ValueError("RCA case must be resolved before it can be closed")
        return self.update(case_id,{"status":"closed","closed_at":_now(),"close_comment":comment},actor,"closed")
