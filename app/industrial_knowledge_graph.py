"""V1.3 industrial knowledge graph and governed causal relations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
import hashlib
from .persistence import Repository

CAUSAL_RELATIONS = {"CAUSED_BY", "RESOLVED_BY"}
EVIDENCE_RELATIONS = {"INDICATED_BY", "DETECTED_BY", "SUPPORTED_BY", "CORRELATED_WITH", "PRECEDES"}
ALL_RELATIONS = CAUSAL_RELATIONS | EVIDENCE_RELATIONS | {"PART_OF", "HAS_COMPONENT", "AFFECTS", "HAS_FAILURE_MODE", "HAS_EFFECT", "DOCUMENTS"}


def _now(): return datetime.now(timezone.utc).isoformat()
def _id(kind: str, label: str): return hashlib.sha1(f"{kind}:{label}".encode()).hexdigest()[:16]

@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    properties: Dict[str, Any]

class IndustrialKnowledgeGraph:
    NODES="industrial_graph_nodes"; EDGES="industrial_graph_edges"
    def __init__(self, repository: Repository): self.repo=repository
    def upsert_node(self, node_type:str, label:str, properties:Optional[Dict[str,Any]]=None, node_id:str=""):
        nid=node_id or _id(node_type,label)
        row={"id":nid,"type":node_type,"label":label,"properties":properties or {},"updated_at":_now()}
        self.repo.put(self.NODES,nid,row); return row
    def upsert_edge(self, source:str, target:str, relation:str, properties:Optional[Dict[str,Any]]=None, provenance:str=""):
        relation=relation.upper()
        if relation not in ALL_RELATIONS: raise ValueError(f"unsupported graph relation: {relation}")
        key=hashlib.sha1(f"{source}:{relation}:{target}:{provenance}".encode()).hexdigest()[:20]
        row={"id":key,"source":source,"target":target,"relation":relation,"properties":properties or {},"provenance":provenance,"updated_at":_now()}
        self.repo.put(self.EDGES,key,row); return row
    def nodes(self, node_type:str="", limit:int=1000):
        rows=self.repo.list(self.NODES,limit=limit)
        return [r for r in rows if not node_type or str(r.get("type",""))==node_type]
    def edges(self, relation:str="", limit:int=5000):
        rows=self.repo.list(self.EDGES,limit=limit)
        return [r for r in rows if not relation or str(r.get("relation",""))==relation.upper()]
    def neighbors(self,node_id:str):
        ns={n["id"]:n for n in self.nodes(limit=5000)}
        out=[]
        for e in self.edges(limit=10000):
            if e.get("source")==node_id: out.append({"direction":"out","edge":e,"node":ns.get(e.get("target"))})
            elif e.get("target")==node_id: out.append({"direction":"in","edge":e,"node":ns.get(e.get("source"))})
        return out
    def find_paths(self,start_id:str,target_type:str,max_depth:int=5,relations:Optional[Iterable[str]]=None):
        allowed={r.upper() for r in relations} if relations else None
        nodes={n["id"]:n for n in self.nodes(limit=5000)}; edges=self.edges(limit=10000)
        q=[(start_id,[],{start_id})]; paths=[]
        while q:
            current,path,seen=q.pop(0)
            if len(path)>=max_depth: continue
            for e in edges:
                if e.get("source")!=current or (allowed and e.get("relation") not in allowed): continue
                nxt=e.get("target"); np=path+[e]
                if nodes.get(nxt,{}).get("type")==target_type: paths.append(np)
                if nxt not in seen: q.append((nxt,np,seen|{nxt}))
        return paths
    def export(self): return {"nodes":self.nodes(limit=5000),"edges":self.edges(limit=10000)}
