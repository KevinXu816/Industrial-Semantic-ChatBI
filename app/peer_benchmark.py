"""V3.8 同类设备对标、可比性解释与 RCA 候选升级服务。"""
from __future__ import annotations
from statistics import median
from typing import Any, Dict, List
import math, uuid

class PeerBenchmarkService:
    ASSESSMENTS="peer_benchmark_assessments"
    def __init__(self, repo): self.repo=repo
    @staticmethod
    def _num(v):
        try:
            x=float(v); return x if math.isfinite(x) else None
        except Exception: return None
    @staticmethod
    def _bucket(value, cuts, labels):
        x=float(value or 0)
        for cut,label in zip(cuts,labels):
            if x<cut:return label
        return labels[-1]
    @classmethod
    def _cluster_parts(cls,row):
        return {
            "product_type": str(row.get("product_type") or "all"),
            "operating_mode": str(row.get("operating_mode") or "all"),
            "load_band": cls._bucket(row.get("load_pct"), [50,80,float("inf")], ["low","mid","high"]),
            "ambient_band": cls._bucket(row.get("ambient_temp"), [20,32,float("inf")], ["cool","normal","hot"]),
        }
    @classmethod
    def _cluster(cls,row):
        p=cls._cluster_parts(row)
        return f"{p['product_type']} · {p['operating_mode']} · {p['load_band']}-load · {p['ambient_band']}"
    @classmethod
    def _comparability(cls,current,peer):
        cp,pp=cls._cluster_parts(current),cls._cluster_parts(peer)
        checks={k:cp[k]==pp[k] for k in cp}
        return {"comparable":all(checks.values()),"checks":checks,"current":cp,"peer":pp}
    def assess(self,payload:Dict[str,Any])->Dict[str,Any]:
        current=dict(payload.get("current") or {}); peers=list(payload.get("peers") or [])
        metric=str(payload.get("metric") or "specific_energy"); current_value=self._num(current.get(metric))
        if current_value is None: raise ValueError(f"current.{metric} 必须是有效数值")
        current_cluster=self._cluster(current)
        comparable=[]; excluded=[]
        for p in peers:
            v=self._num(p.get(metric)); comp=self._comparability(current,p)
            if v is None:
                excluded.append({"asset_id":p.get("asset_id"),"reason":"metric_invalid","comparability":comp}); continue
            if not p.get("baseline_eligible",True):
                excluded.append({"asset_id":p.get("asset_id"),"reason":"baseline_ineligible","comparability":comp}); continue
            if comp["comparable"]: comparable.append(dict(p))
            else: excluded.append({"asset_id":p.get("asset_id"),"reason":"operating_context_mismatch","comparability":comp})
        values=[float(x[metric]) for x in comparable]
        base=float(median(values)) if values else None
        deviation=None if base in (None,0) else (current_value-base)/abs(base)*100
        ranked=sorted(comparable,key=lambda x: float(x[metric]))
        rank=1+sum(1 for x in values if x<current_value) if values else None
        percentile=None if not values else round(100*(rank-1)/max(len(values),1),1)
        best=ranked[0] if ranked else None
        gap=None if not best or self._num(best.get(metric)) in (None,0) else (current_value-float(best[metric]))/abs(float(best[metric]))*100
        ready=len(values)>=3
        priority_score=0.0
        if ready:
            priority_score=min(100.0,max(0.0,(max(0.0,deviation or 0)*2.4)+(max(0.0,percentile or 0)*0.55)))
        priority="P1" if priority_score>=80 else ("P2" if priority_score>=60 else ("P3" if priority_score>=35 else "P4"))
        result={
          "assessment_id":"PB-"+uuid.uuid4().hex[:12].upper(),"metric":metric,"cluster":current_cluster,
          "cluster_dimensions":self._cluster_parts(current),"peer_count":len(peers),"comparable_peer_count":len(values),
          "excluded_peer_count":len(excluded),"peer_median":None if base is None else round(base,4),
          "current_asset":current.get("asset_id"),"current_value":current_value,"deviation_vs_peer_median_pct":None if deviation is None else round(deviation,2),
          "percentile":percentile,"best_peer":best,"gap_to_best_pct":None if gap is None else round(gap,2),
          "ready":ready,"rca_candidate":bool(ready and (deviation or 0)>=10 and (percentile or 0)>=60),
          "priority_score":round(priority_score,1),"priority":priority,"comparable_peers":ranked[:50],"excluded_peers":excluded[:50],
          "comparability_explanation":{
              "dimensions":["product_type","operating_mode","load_band","ambient_band"],
              "rule":"产品类型、运行模式、负荷区间和环境温度区间必须一致，且 Peer 必须 baseline_eligible。",
              "excluded_reasons":sorted({x["reason"] for x in excluded})
          },
          "recommendation":"优先分析同工况下单位能耗显著高于同类设备中位数的设备，并结合 V3.5 数据质量、V3.6 历史基线和 FMEA 证据进入 RCA。"
        }
        self.repo.put(self.ASSESSMENTS,result["assessment_id"],result); return result
    def get(self,assessment_id): return self.repo.get(self.ASSESSMENTS,assessment_id)
    def assessments(self,limit=200): return self.repo.list(self.ASSESSMENTS,limit=limit)
