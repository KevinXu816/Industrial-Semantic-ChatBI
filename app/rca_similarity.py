"""Similarity search over confirmed RCA cases using deterministic embeddings + lexical evidence."""
from __future__ import annotations
import math
from .historical_rca import _terms
from .knowledge_embeddings import HashingEmbeddingProvider, cosine_similarity
class RCASimilaritySearch:
    def __init__(self,repository,embedder=None): self.repo=repository; self.embedder=embedder or HashingEmbeddingProvider()
    def search(self,query:str,subject=None,top_k:int=5):
        qterms=_terms(query); qvec=self.embedder.embed(query); out=[]
        for c in self.repo.list("rca_cases",limit=1000):
            if c.get("status") not in {"reviewed","resolved","closed"} or not c.get("confirmed_root_cause"): continue
            text=" ".join([str(c.get("title","")),str(c.get("question","")),str(c.get("confirmed_root_cause","")),str((c.get("resolution") or {}).get("action","")),str((c.get("resolution") or {}).get("comment",""))])
            dterms=_terms(text); lex=len(qterms&dterms)/max(1.0,math.sqrt(max(1,len(qterms))*max(1,len(dterms))))
            vec=max(0.0,cosine_similarity(qvec,self.embedder.embed(text))); subj_bonus=0.0
            if subject and c.get("subject"):
                if str(subject.get("entity"))==str(c["subject"].get("entity")): subj_bonus+=0.05
                if str(subject.get("reference"))==str(c["subject"].get("reference")): subj_bonus+=0.1
            score=min(1.0,0.55*lex+0.45*vec+subj_bonus)
            if score<=0: continue
            out.append({"case_id":c.get("case_id"),"title":c.get("title"),"subject":c.get("subject"),"confirmed_root_cause":c.get("confirmed_root_cause"),"resolution":c.get("resolution"),"similarity_score":round(score,4),"lexical_score":round(lex,4),"vector_score":round(vec,4),"provenance":f"rca_case:{c.get('case_id')}"})
        out.sort(key=lambda x:x["similarity_score"],reverse=True); return out[:max(1,min(int(top_k),20))]
