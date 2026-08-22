"""V1.4 governed FMEA domain model and repository-backed studio service."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
from .persistence import Repository
from .enterprise_identity import default_tenant_id

VALID_STATUS={"draft","candidate","approved","superseded","retired","rejected"}

def _now(): return datetime.now(timezone.utc).isoformat()
def _score(value:Any,name:str)->int:
    try: n=int(value)
    except Exception as exc: raise ValueError(f"{name} must be an integer from 1 to 10") from exc
    if not 1 <= n <= 10: raise ValueError(f"{name} must be between 1 and 10")
    return n

def risk_class(rpn:int,severity:int)->str:
    # Conservative default policy; enterprises can later externalize these thresholds.
    if severity >= 9 or rpn >= 300: return "critical"
    if rpn >= 160: return "high"
    if rpn >= 80: return "medium"
    return "low"

class FMEAStore:
    COLLECTION="fmea_records"
    def __init__(self,repository:Repository): self.repo=repository
    def _normalize(self,payload:Dict[str,Any],existing:Optional[Dict[str,Any]]=None)->Dict[str,Any]:
        row=dict(existing or {}); row.update(payload or {})
        fid=str(row.get("fmea_id") or row.get("id") or "").strip()
        if not fid:
            basis=f"{row.get('asset','')}:{row.get('component','')}:{row.get('failure_mode','')}:{row.get('cause','')}"
            fid="FMEA-"+hashlib.sha1(basis.encode()).hexdigest()[:10].upper()
        row["fmea_id"]=fid; row["id"]=fid
        for req in ("failure_mode","component"):
            if not str(row.get(req,"" )).strip(): raise ValueError(f"{req} is required")
        s=_score(row.get("severity",1),"severity"); o=_score(row.get("occurrence",1),"occurrence"); d=_score(row.get("detectability",1),"detectability")
        row.update({"severity":s,"occurrence":o,"detectability":d,"rpn":s*o*d})
        row["criticality"]=risk_class(row["rpn"],s)
        status=str(row.get("status","draft")).lower()
        if status not in VALID_STATUS: raise ValueError(f"unsupported FMEA status: {status}")
        row["status"]=status; row.setdefault("version","1.0")
        row.setdefault("tenant_id", default_tenant_id()); row.setdefault("org_id", ""); row.setdefault("site_id", "")
        row.setdefault("created_at",_now()); row["updated_at"]=_now()
        return row
    def create(self,payload:Dict[str,Any],actor:str="engineer"):
        row=self._normalize(payload); row["created_by"]=actor
        row.setdefault("history",[]); row["history"].append({"at":_now(),"action":"created","actor":actor,"status":row["status"]})
        return self.repo.put(self.COLLECTION,row["fmea_id"],row)
    def get(self,fmea_id:str): return self.repo.get(self.COLLECTION,fmea_id)
    def update(self,fmea_id:str,payload:Dict[str,Any],actor:str="engineer"):
        existing=self.get(fmea_id)
        if not existing: raise KeyError(fmea_id)
        row=self._normalize({**payload,"fmea_id":fmea_id},existing); row.setdefault("history",[]); row["history"].append({"at":_now(),"action":"updated","actor":actor,"status":row["status"]})
        return self.repo.put(self.COLLECTION,fmea_id,row)
    def approve(self,fmea_id:str,actor:str="reliability_engineer"):
        row=self.get(fmea_id)
        if not row: raise KeyError(fmea_id)
        if row.get("status") in {"retired","rejected"}: raise ValueError(f"cannot approve FMEA in status {row.get('status')}")
        row["status"]="approved"; row["approved_by"]=actor; row["approved_at"]=_now(); row["updated_at"]=_now(); row.setdefault("history",[]).append({"at":_now(),"action":"approved","actor":actor,"status":"approved"})
        return self.repo.put(self.COLLECTION,fmea_id,row)
    def retire(self,fmea_id:str,actor:str="reliability_engineer",reason:str=""):
        row=self.get(fmea_id)
        if not row: raise KeyError(fmea_id)
        row["status"]="retired"; row["retired_reason"]=reason; row["updated_at"]=_now(); row.setdefault("history",[]).append({"at":_now(),"action":"retired","actor":actor,"reason":reason,"status":"retired"})
        return self.repo.put(self.COLLECTION,fmea_id,row)
    def list(self,limit:int=100,status:str="",asset:str="",component:str=""):
        rows=self.repo.list(self.COLLECTION,limit=min(max(limit*5,100),1000))
        def ok(r):
            return (not status or r.get("status")==status) and (not asset or str(r.get("asset",""))==asset) and (not component or str(r.get("component",""))==component)
        return [r for r in rows if ok(r)][:limit]
    def rank(self,limit:int=20,status:str="approved"):
        rows=self.list(limit=1000,status=status)
        rows.sort(key=lambda x:(int(x.get("severity",0)),int(x.get("rpn",0))),reverse=True)
        return rows[:limit]
    def stats(self):
        rows=self.repo.list(self.COLLECTION,limit=1000)
        by_status={}; by_criticality={}
        for r in rows:
            by_status[r.get("status","unknown")]=by_status.get(r.get("status","unknown"),0)+1
            by_criticality[r.get("criticality","unknown")]=by_criticality.get(r.get("criticality","unknown"),0)+1
        approved=[r for r in rows if r.get("status")=="approved"]
        return {"records":len(rows),"approved":len(approved),"by_status":by_status,"by_criticality":by_criticality,"max_rpn":max([int(r.get("rpn",0)) for r in approved] or [0])}
