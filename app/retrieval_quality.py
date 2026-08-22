"""Offline retrieval evaluation and lightweight RCA ranking calibration."""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, Iterable, List

class RetrievalEvaluator:
    def __init__(self,retriever): self.retriever=retriever
    def evaluate(self,cases:Iterable[Dict[str,Any]],top_k:int=5):
        rows=[]; hits=0; rr=0.0
        for case in cases:
            q=str(case.get("query") or ""); expected={str(x) for x in (case.get("expected_ids") or [])}
            results=self.retriever.search(q,top_k=top_k,filters=case.get("filters"))
            ids=[str(r.get("document_id") or r.get("id") or "") for r in results]
            rank=next((i+1 for i,x in enumerate(ids) if x in expected),None)
            if rank: hits+=1; rr+=1.0/rank
            rows.append({"query":q,"expected_ids":sorted(expected),"returned_ids":ids,"hit":bool(rank),"first_relevant_rank":rank})
        n=len(rows)
        return {"queries":n,"top_k":top_k,"recall_at_k":round(hits/n,4) if n else 0.0,"mrr":round(rr/n,4) if n else 0.0,"details":rows}

class RCARankingCalibrator:
    """Derive transparent cause multipliers from accepted/rejected engineer feedback."""
    def __init__(self,feedback_store): self.feedback_store=feedback_store
    def weights(self,limit=1000):
        stats=defaultdict(lambda:{"accepted":0,"rejected":0,"corrected":0})
        for row in self.feedback_store.list(limit):
            predicted=str(row.get("predicted_cause") or "")
            correct=str(row.get("correct_cause") or "")
            if predicted:
                if row.get("accepted") is True: stats[predicted]["accepted"]+=1
                elif row.get("accepted") is False: stats[predicted]["rejected"]+=1
            if correct: stats[correct]["corrected"]+=1
        out={}
        for cause,s in stats.items():
            pos=s["accepted"]+s["corrected"]; neg=s["rejected"]
            # Bayesian-smoothed, bounded adjustment; never overrides evidence.
            precision=(pos+2)/(pos+neg+4)
            multiplier=max(0.75,min(1.25,0.75+precision*0.5))
            out[cause]={**s,"multiplier":round(multiplier,4)}
        return out
    def calibrate(self,hypotheses:List[Dict[str,Any]]):
        weights=self.weights(); out=[]
        for h in hypotheses:
            row=dict(h); cause=str(row.get("cause_code") or row.get("cause") or "")
            mult=float(weights.get(cause,{}).get("multiplier",1.0)); base=float(row.get("confidence",0))
            row["base_confidence"]=base; row["calibration_multiplier"]=mult; row["confidence"]=round(min(0.99,max(0.0,base*mult)),4); out.append(row)
        out.sort(key=lambda x:x.get("confidence",0),reverse=True)
        for i,r in enumerate(out,1): r["rank"]=i
        return out
