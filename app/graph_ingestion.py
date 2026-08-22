"""Promote governed knowledge and confirmed RCA cases into the industrial graph."""
from __future__ import annotations
from typing import Any, Dict
from .industrial_knowledge_graph import IndustrialKnowledgeGraph

class GraphIngestionService:
    def __init__(self, graph:IndustrialKnowledgeGraph): self.graph=graph
    def ingest_knowledge(self, doc:Dict[str,Any]):
        if str(doc.get("status","approved")).lower()!="approved": return {"status":"skipped","reason":"knowledge_not_approved"}
        prov=str(doc.get("provenance") or doc.get("citation") or f"knowledge:{doc.get('id')}@{doc.get('version','1.0')}")
        kn=self.graph.upsert_node("Knowledge",str(doc.get("title") or doc.get("id")),{"document_id":doc.get("id"),"version":doc.get("version"),"citation":doc.get("citation")})
        fm=doc.get("failure_mode") or doc.get("cause_code")
        created=[kn]
        if fm:
            fn=self.graph.upsert_node("FailureMode",str(fm),{"cause_code":str(fm)}); created.append(fn)
            self.graph.upsert_edge(fn["id"],kn["id"],"SUPPORTED_BY",provenance=prov)
        for alarm in doc.get("alarm_patterns") or []:
            an=self.graph.upsert_node("Alarm",str(alarm)); created.append(an)
            if fm: self.graph.upsert_edge(fn["id"],an["id"],"INDICATED_BY",provenance=prov)
        for sensor in doc.get("sensor_patterns") or []:
            sn=self.graph.upsert_node("SensorPattern",str(sensor)); created.append(sn)
            if fm: self.graph.upsert_edge(fn["id"],sn["id"],"DETECTED_BY",provenance=prov)
        for comp in doc.get("components") or []:
            cn=self.graph.upsert_node("Component",str(comp)); created.append(cn)
            if fm: self.graph.upsert_edge(fn["id"],cn["id"],"CAUSED_BY",provenance=prov)
        for action in doc.get("recommended_actions") or []:
            rn=self.graph.upsert_node("MaintenanceAction",str(action)); created.append(rn)
            if fm: self.graph.upsert_edge(fn["id"],rn["id"],"RESOLVED_BY",provenance=prov)
        return {"status":"ingested","nodes":len(created),"provenance":prov}
    def ingest_rca_case(self,case:Dict[str,Any]):
        root=case.get("confirmed_root_cause") or (case.get("resolution") or {}).get("confirmed_root_cause")
        if not root: return {"status":"skipped","reason":"root_cause_not_confirmed"}
        prov=f"rca_case:{case.get('case_id')}"
        fn=self.graph.upsert_node("FailureMode",str(root),{"cause_code":str(root)})
        cn=self.graph.upsert_node("RCACase",str(case.get("case_id")),{"question":case.get("question"),"status":case.get("status")})
        self.graph.upsert_edge(fn["id"],cn["id"],"SUPPORTED_BY",provenance=prov)
        action=(case.get("resolution") or {}).get("action") or case.get("action")
        if action:
            an=self.graph.upsert_node("MaintenanceAction",str(action)); self.graph.upsert_edge(fn["id"],an["id"],"RESOLVED_BY",provenance=prov)
        return {"status":"ingested","failure_mode_id":fn["id"],"provenance":prov}
