"""V2.8 unified enterprise audit, compliance and policy center.

The center normalizes native audit events and legacy audit collections without
forcing older modules to rewrite their storage contracts in one release.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional
import csv, io, json, uuid
from .persistence import Repository
from .enterprise_identity import default_tenant_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: Any, max_len: int = 2000) -> Any:
    if isinstance(value, dict):
        blocked={"password","passwd","pwd","api_key","apikey","token","access_token","client_secret","secret","private_key","authorization"}
        return {k:("***" if str(k).lower() in blocked else _safe(v,max_len)) for k,v in value.items()}
    if isinstance(value, list): return [_safe(v,max_len) for v in value[:200]]
    if isinstance(value, str) and len(value)>max_len: return value[:max_len]+"…"
    return value


class AuditCenter:
    EVENTS="enterprise_audit_events"
    POLICIES="compliance_policies"
    VIOLATIONS="compliance_violations"
    RETENTION="audit_retention_policy"

    def __init__(self, repo: Repository):
        self.repo=repo
        if not self.repo.get(self.RETENTION,"default"):
            self.repo.put(self.RETENTION,"default",{"policy_id":"default","retention_days":365,"updated_at":_now(),"updated_by":"bootstrap"})

    def emit(self, *, category:str, action:str, actor:str="system", tenant_id:str="", org_id:str="", site_id:str="",
             resource_type:str="", resource_id:str="", decision:str="allow", status:str="success", correlation_id:str="",
             before:Any=None, after:Any=None, detail:Any=None, provenance:Any=None, source:str="platform") -> Dict[str,Any]:
        eid="AUD-"+uuid.uuid4().hex[:18].upper()
        row={"event_id":eid,"category":category,"action":action,"actor":actor or "anonymous",
             "tenant_id":tenant_id or default_tenant_id(),"org_id":org_id or "","site_id":site_id or "",
             "resource_type":resource_type or "","resource_id":resource_id or "","decision":decision or "allow",
             "status":status or "success","correlation_id":correlation_id or "","before":_safe(before),"after":_safe(after),
             "detail":_safe(detail),"provenance":_safe(provenance),"source":source,"created_at":_now()}
        self.repo.put(self.EVENTS,eid,row)
        self._evaluate_native_event(row)
        return row

    def search(self, *, actor:str="", tenant_id:str="", category:str="", action:str="", decision:str="", status:str="",
               resource_type:str="", resource_id:str="", correlation_id:str="", since:str="", until:str="", limit:int=200) -> List[Dict[str,Any]]:
        rows=self.repo.list(self.EVENTS,limit=5000)
        def ok(r):
            if actor and r.get("actor")!=actor: return False
            if tenant_id and r.get("tenant_id")!=tenant_id: return False
            if category and r.get("category")!=category: return False
            if action and r.get("action")!=action: return False
            if decision and r.get("decision")!=decision: return False
            if status and r.get("status")!=status: return False
            if resource_type and r.get("resource_type")!=resource_type: return False
            if resource_id and r.get("resource_id")!=resource_id: return False
            if correlation_id and r.get("correlation_id")!=correlation_id: return False
            ts=str(r.get("created_at") or "")
            if since and ts<since: return False
            if until and ts>until: return False
            return True
        return [r for r in rows if ok(r)][:max(1,min(limit,2000))]

    def trace(self, correlation_id:str) -> List[Dict[str,Any]]:
        rows=self.search(correlation_id=correlation_id,limit=2000)
        return sorted(rows,key=lambda x:x.get("created_at", ""))

    def add_policy(self,payload:Dict[str,Any],actor="compliance_admin"):
        pid=str(payload.get("policy_id") or "POL-"+uuid.uuid4().hex[:12].upper())
        row={"policy_id":pid,"name":str(payload.get("name") or pid),"enabled":bool(payload.get("enabled",True)),
             "match":payload.get("match") or {},"severity":str(payload.get("severity") or "medium"),
             "description":str(payload.get("description") or ""),"updated_at":_now(),"updated_by":actor}
        return self.repo.put(self.POLICIES,pid,row)

    def policies(self,limit=200): return self.repo.list(self.POLICIES,limit=limit)

    def _matches(self,row,match):
        for k,v in (match or {}).items():
            rv=row.get(k)
            vals=v if isinstance(v,list) else [v]
            if rv not in vals: return False
        return True

    def _violate(self,event:Dict[str,Any],policy_id:str,severity:str,reason:str):
        raw=f"{event.get('event_id')}:{policy_id}"
        vid="VIO-"+uuid.uuid5(uuid.NAMESPACE_URL,raw).hex[:16].upper()
        existing=self.repo.get(self.VIOLATIONS,vid)
        if existing: return existing
        row={"violation_id":vid,"policy_id":policy_id,"event_id":event.get("event_id"),"severity":severity,
             "reason":reason,"status":"open","tenant_id":event.get("tenant_id"),"correlation_id":event.get("correlation_id"),
             "created_at":_now()}
        return self.repo.put(self.VIOLATIONS,vid,row)

    def _evaluate_native_event(self,event):
        if event.get("decision")=="deny" or event.get("status")=="failure":
            self._violate(event,"builtin-deny-failure","high" if event.get("category") in {"authentication","secret"} else "medium",
                          "Denied or failed governed operation")
        for p in self.policies(limit=1000):
            if p.get("enabled") and self._matches(event,p.get("match") or {}):
                self._violate(event,p["policy_id"],p.get("severity","medium"),p.get("description") or p.get("name") or "policy matched")

    def violations(self,status="",severity="",limit=500):
        rows=self.repo.list(self.VIOLATIONS,limit=2000)
        return [r for r in rows if (not status or r.get("status")==status) and (not severity or r.get("severity")==severity)][:limit]

    def resolve_violation(self,violation_id,actor="compliance_admin",comment=""):
        row=self.repo.get(self.VIOLATIONS,violation_id)
        if not row: raise KeyError(violation_id)
        row.update({"status":"resolved","resolved_at":_now(),"resolved_by":actor,"resolution_comment":comment})
        return self.repo.put(self.VIOLATIONS,violation_id,row)

    def set_retention(self,days:int,actor="compliance_admin"):
        days=max(1,min(int(days),3650))
        return self.repo.put(self.RETENTION,"default",{"policy_id":"default","retention_days":days,"updated_at":_now(),"updated_by":actor})
    def retention(self): return self.repo.get(self.RETENTION,"default") or {"retention_days":365}

    def enforce_retention(self,dry_run=True):
        days=int(self.retention().get("retention_days",365)); cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        old=[r for r in self.repo.list(self.EVENTS,limit=5000) if str(r.get("created_at") or "")<cutoff]
        if not dry_run:
            for r in old: self.repo.delete(self.EVENTS,r["event_id"])
        return {"retention_days":days,"eligible":len(old),"deleted":0 if dry_run else len(old),"dry_run":bool(dry_run)}

    def summary(self):
        rows=self.repo.list(self.EVENTS,limit=5000); v=self.violations(limit=5000)
        by_cat={}; denies=0; failures=0
        for r in rows:
            c=r.get("category","unknown"); by_cat[c]=by_cat.get(c,0)+1
            denies+=r.get("decision")=="deny"; failures+=r.get("status")=="failure"
        return {"events":len(rows),"denies":int(denies),"failures":int(failures),"open_violations":sum(x.get("status")=="open" for x in v),"by_category":by_cat,"retention":self.retention()}

    def export(self,fmt="json",**filters):
        rows=self.search(limit=2000,**filters)
        if fmt.lower()=="csv":
            cols=["event_id","created_at","correlation_id","actor","tenant_id","category","action","resource_type","resource_id","decision","status","source"]
            out=io.StringIO(); w=csv.DictWriter(out,fieldnames=cols); w.writeheader();
            for r in rows: w.writerow({k:r.get(k,"") for k in cols})
            return out.getvalue()
        return json.dumps(rows,ensure_ascii=False,indent=2,default=str)

    def import_legacy(self,limit_each=1000):
        """Idempotently normalize the important V2.x audit/history collections."""
        sources=[
            ("authentication_audit","authentication"),("enterprise_access_audit","authorization"),("secret_access_audit","secret"),
            ("runtime_queries","semantic_query"),("connector_batches","connector"),("integration_dead_letters","data_quality")]
        imported=0
        for collection,category in sources:
            for r in self.repo.list(collection,limit=limit_each):
                source_id=str(r.get("audit_id") or r.get("query_id") or r.get("batch_id") or r.get("dead_letter_id") or "")
                if not source_id: continue
                eid=f"LEGACY:{collection}:{source_id}"
                if self.repo.get(self.EVENTS,eid): continue
                decision="deny" if r.get("allowed") is False else "allow"
                status="failure" if r.get("success") is False or collection=="integration_dead_letters" else "success"
                action=str(r.get("action") or r.get("reason") or collection)
                actor=str(r.get("principal_id") or r.get("principal") or r.get("user") or r.get("created_by") or "system")
                row={"event_id":eid,"category":category,"action":action,"actor":actor,"tenant_id":str(r.get("tenant_id") or default_tenant_id()),
                     "org_id":str(r.get("org_id") or ""),"site_id":str(r.get("site_id") or ""),"resource_type":str(r.get("resource_type") or collection),
                     "resource_id":str(r.get("resource_id") or r.get("binding_id") or r.get("secret_id") or ""),"decision":decision,"status":status,
                     "correlation_id":str(r.get("correlation_id") or ""),"before":None,"after":None,"detail":_safe(r),"provenance":{"legacy_collection":collection},
                     "source":"legacy_adapter","created_at":str(r.get("created_at") or r.get("at") or _now())}
                self.repo.put(self.EVENTS,eid,row); self._evaluate_native_event(row); imported+=1
        return {"imported":imported}
