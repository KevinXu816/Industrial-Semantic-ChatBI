"""V1.2 governed knowledge lifecycle and RCA-to-knowledge promotion workflow."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .knowledge_store import KnowledgeStore
from .persistence import Repository

VALID_STATUS={"draft","candidate","approved","superseded","retired","rejected"}
def _now(): return datetime.now(timezone.utc).isoformat()

class KnowledgeWorkflow:
    CANDIDATES="knowledge_candidates"
    def __init__(self, store: KnowledgeStore, repository: Repository, ingestion=None):
        self.store=store; self.repo=repository; self.ingestion=ingestion

    def submit_document(self, document: Dict[str,Any], actor="knowledge_engineer"):
        doc=dict(document); doc.setdefault("status","candidate")
        result=self.store.put_document(doc, actor=actor)
        return result

    def approve(self, document_id:str, version:str, actor="knowledge_approver", effective_from:Optional[str]=None):
        doc=self.store.get_document(document_id,version)
        if not doc: raise KeyError(f"{document_id}@{version}")
        doc={**doc,"status":"approved","approved_by":actor,"approved_at":_now(),"effective_from":effective_from or _now(),"updated_at":_now(),"updated_by":actor}
        result=self.store.replace_document(doc, actor=actor)
        if self.ingestion and self.ingestion.backend is not None: self.ingestion.backend.upsert_chunks(result["chunks"])
        return result

    def retire(self, document_id:str, version:str, actor="knowledge_approver", reason=""):
        doc=self.store.get_document(document_id,version)
        if not doc: raise KeyError(f"{document_id}@{version}")
        doc={**doc,"status":"retired","retired_by":actor,"retired_at":_now(),"retire_reason":reason,"effective_to":_now()}
        result=self.store.replace_document(doc, actor=actor)
        if self.ingestion and self.ingestion.backend is not None: self.ingestion.backend.upsert_chunks(result["chunks"])
        return result

    def supersede(self, document_id:str, old_version:str, new_document:Dict[str,Any], actor="knowledge_approver"):
        old=self.store.get_document(document_id,old_version)
        if not old: raise KeyError(f"{document_id}@{old_version}")
        new_doc=dict(new_document); new_doc["id"]=document_id; new_doc.setdefault("status","approved")
        new_result=self.store.put_document(new_doc,actor=actor)
        old={**old,"status":"superseded","superseded_by":new_result["document"]["citation"],"effective_to":_now(),"updated_at":_now(),"updated_by":actor}
        old_result=self.store.replace_document(old,actor=actor)
        if self.ingestion and self.ingestion.backend is not None:
            self.ingestion.backend.upsert_chunks(old_result["chunks"] + new_result["chunks"])
        return {"superseded":old,"replacement":new_result}

    def candidate_from_case(self, case:Dict[str,Any], actor="engineer"):
        cause=case.get("confirmed_root_cause")
        if not cause: raise ValueError("RCA case must have confirmed_root_cause")
        cid=f"KC-{case['case_id']}"
        resolution=case.get("resolution") or {}
        rec={"candidate_id":cid,"status":"candidate","source_case_id":case["case_id"],"subject":case.get("subject"),
             "title":case.get("title") or case.get("question"),"question":case.get("question",""),"confirmed_root_cause":cause,
             "resolution":resolution,"created_by":actor,"created_at":_now(),"updated_at":_now()}
        return self.repo.put(self.CANDIDATES,cid,rec)

    def list_candidates(self,limit=100,status=""):
        rows=self.repo.list(self.CANDIDATES,limit=1000)
        if status: rows=[r for r in rows if r.get("status")==status]
        return rows[:max(1,min(int(limit),500))]

    def promote_candidate(self,candidate_id:str,document:Dict[str,Any]|None=None,actor="knowledge_approver"):
        c=self.repo.get(self.CANDIDATES,candidate_id)
        if not c: raise KeyError(candidate_id)
        doc=dict(document or {})
        doc.setdefault("id",f"RCA-KNOWLEDGE-{c['source_case_id']}")
        doc.setdefault("version","1.0")
        doc.setdefault("type","HistoricalRCAKnowledge")
        doc.setdefault("title",c.get("title") or c["source_case_id"])
        doc.setdefault("failure_mode",c.get("confirmed_root_cause"))
        resolution=c.get("resolution") or {}
        doc.setdefault("content",f"问题: {c.get('question','')}\n确认根因: {c.get('confirmed_root_cause')}\n处理措施: {resolution.get('action','')}\n处理结果: {resolution.get('comment','')}")
        doc.setdefault("tags",[str(c.get("confirmed_root_cause")),"confirmed_rca","promoted_knowledge"])
        doc["status"]="approved"; doc["source_case_id"]=c["source_case_id"]; doc["approved_by"]=actor; doc["approved_at"]=_now(); doc["effective_from"]=_now()
        result=self.store.put_document(doc,actor=actor)
        if self.ingestion and self.ingestion.backend is not None:
            self.ingestion.backend.upsert_chunks(result["chunks"])
        c={**c,"status":"approved","promoted_document":result["document"]["citation"],"approved_by":actor,"approved_at":_now(),"updated_at":_now()}
        self.repo.put(self.CANDIDATES,candidate_id,c)
        return {"candidate":c,"knowledge":result}
