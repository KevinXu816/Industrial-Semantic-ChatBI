"""V1.4 bridge from approved FMEA records into the industrial failure graph."""
from __future__ import annotations
from typing import Any, Dict
from .industrial_knowledge_graph import IndustrialKnowledgeGraph

class FailureModelIngestion:
    def __init__(self,graph:IndustrialKnowledgeGraph): self.graph=graph
    def ingest_fmea(self,row:Dict[str,Any]):
        if str(row.get("status","draft"))!="approved": return {"status":"skipped","reason":"fmea_not_approved"}
        prov=f"fmea:{row.get('fmea_id')}@{row.get('version','1.0')}"
        asset=None
        if row.get("asset"):
            asset=self.graph.upsert_node("Asset",str(row["asset"]),{"asset_id":row.get("asset_id") or row.get("asset")})
        comp=self.graph.upsert_node("Component",str(row.get("component")),{"component_id":row.get("component_id") or row.get("component")})
        if asset: self.graph.upsert_edge(asset["id"],comp["id"],"HAS_COMPONENT",provenance=prov)
        fm=self.graph.upsert_node("FailureMode",str(row.get("failure_mode")),{
            "cause_code":row.get("cause_code") or row.get("failure_mode"),"fmea_id":row.get("fmea_id"),"severity":row.get("severity"),"occurrence":row.get("occurrence"),"detectability":row.get("detectability"),"rpn":row.get("rpn"),"criticality":row.get("criticality")})
        self.graph.upsert_edge(comp["id"],fm["id"],"HAS_FAILURE_MODE",provenance=prov)
        if row.get("cause"):
            cause=self.graph.upsert_node("FailureCause",str(row["cause"])); self.graph.upsert_edge(fm["id"],cause["id"],"CAUSED_BY",provenance=prov)
        if row.get("effect"):
            effect=self.graph.upsert_node("FailureEffect",str(row["effect"])); self.graph.upsert_edge(fm["id"],effect["id"],"HAS_EFFECT",provenance=prov)
        detection=row.get("detection_method") or row.get("detection")
        if detection:
            dn=self.graph.upsert_node("DetectionMethod",str(detection)); self.graph.upsert_edge(fm["id"],dn["id"],"DETECTED_BY",provenance=prov)
        for alarm in row.get("alarm_patterns") or []:
            an=self.graph.upsert_node("Alarm",str(alarm)); self.graph.upsert_edge(fm["id"],an["id"],"INDICATED_BY",provenance=prov)
        action=row.get("recommended_action")
        if action:
            ac=self.graph.upsert_node("MaintenanceAction",str(action)); self.graph.upsert_edge(fm["id"],ac["id"],"RESOLVED_BY",provenance=prov)
        return {"status":"ingested","failure_mode_id":fm["id"],"provenance":prov,"rpn":row.get("rpn"),"criticality":row.get("criticality")}
