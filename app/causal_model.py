"""Governed graph-based RCA reasoning. Causal claims require governed causal edges."""
from __future__ import annotations
from typing import Any, Dict, List
from .industrial_knowledge_graph import IndustrialKnowledgeGraph, CAUSAL_RELATIONS

REL_WEIGHT={"CAUSED_BY":1.0,"INDICATED_BY":0.78,"DETECTED_BY":0.72,"SUPPORTED_BY":0.65,"CORRELATED_WITH":0.45,"PRECEDES":0.35,"RESOLVED_BY":0.90,"AFFECTS":0.70,"PART_OF":0.50,"HAS_COMPONENT":0.50,"HAS_FAILURE_MODE":0.70,"DOCUMENTS":0.45,"HAS_EFFECT":0.55}

class CausalGraphReasoner:
    def __init__(self, graph:IndustrialKnowledgeGraph): self.graph=graph
    def rank_failure_modes(self, evidence_terms:List[str], top_k:int=5)->List[Dict[str,Any]]:
        terms=[str(x).lower() for x in evidence_terms if x]
        nodes={n["id"]:n for n in self.graph.nodes(limit=5000)}
        edges=self.graph.edges(limit=10000); scores={}; supports={}
        evidence_ids=[]
        for nid,n in nodes.items():
            hay=(str(n.get("label",""))+" "+str(n.get("properties",{}))).lower()
            if any(t in hay for t in terms): evidence_ids.append(nid)
        for e in edges:
            s,t=e.get("source"),e.get("target"); rel=e.get("relation")
            # Evidence nodes point to or are pointed from failure modes depending on semantic relation.
            for ev,fm in ((s,t),(t,s)):
                if ev in evidence_ids and nodes.get(fm,{}).get("type")=="FailureMode":
                    w=REL_WEIGHT.get(rel,0.3); scores[fm]=scores.get(fm,0)+w
                    supports.setdefault(fm,[]).append({"evidence_node":nodes.get(ev),"relation":rel,"provenance":e.get("provenance"),"weight":w})
        out=[]
        for fid,score in scores.items():
            causal=any(s["relation"] in CAUSAL_RELATIONS for s in supports[fid])
            out.append({"failure_mode_id":fid,"cause_code":nodes[fid].get("properties",{}).get("cause_code") or nodes[fid].get("label"),"cause":nodes[fid].get("label"),"graph_score":round(min(score/2.0,0.95),3),"supports":supports[fid],"causal_claim_supported":causal})
        out.sort(key=lambda x:x["graph_score"],reverse=True)
        for i,x in enumerate(out[:top_k],1): x["rank"]=i
        return out[:top_k]
    def explain_path(self,failure_mode_id:str)->Dict[str,Any]:
        node=next((n for n in self.graph.nodes(limit=5000) if n.get("id")==failure_mode_id),None)
        if not node: return {"status":"not_found","paths":[]}
        paths=[]
        for e in self.graph.edges(limit=10000):
            if e.get("source")==failure_mode_id or e.get("target")==failure_mode_id:
                paths.append(e)
        return {"status":"ok","failure_mode":node,"relations":paths}
