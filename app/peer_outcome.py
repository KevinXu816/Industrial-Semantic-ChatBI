"""V3.9 Peer Benchmark -> RCA -> Maintenance -> Outcome verification closed loop."""
from __future__ import annotations
from statistics import median
from typing import Any, Dict, List
from datetime import datetime, timezone
import math, uuid


def _now(): return datetime.now(timezone.utc).isoformat()

class PeerOutcomeService:
    COLLECTION = "peer_benchmark_outcomes"
    POLICY = "peer_outcome_policy"
    def __init__(self, repo, peer_benchmark, rca_cases):
        self.repo=repo; self.peer_benchmark=peer_benchmark; self.rca_cases=rca_cases
        if not self.repo.get(self.POLICY,"default"):
            self.repo.put(self.POLICY,"default",{
                "policy_id":"default","minimum_improvement_pct":5.0,
                "maximum_peer_deviation_after_pct":10.0,"minimum_verification_samples":3,
                "require_same_operating_cluster":True,"updated_at":_now()
            })
    def policy(self): return self.repo.get(self.POLICY,"default") or {}
    def upsert_policy(self,payload):
        row={**self.policy(),**payload,"policy_id":"default","updated_at":_now()}
        for k in ("minimum_improvement_pct","maximum_peer_deviation_after_pct"):
            row[k]=float(row.get(k,0))
        row["minimum_verification_samples"]=max(1,int(row.get("minimum_verification_samples",3)))
        return self.repo.put(self.POLICY,"default",row)
    @staticmethod
    def _num(v):
        try:
            x=float(v); return x if math.isfinite(x) else None
        except Exception:return None
    def verify(self, assessment_id:str, payload:Dict[str,Any])->Dict[str,Any]:
        a=self.peer_benchmark.get(assessment_id)
        if not a: raise KeyError(assessment_id)
        metric=str(a.get("metric") or "specific_energy"); cluster=a.get("cluster_dimensions") or {}
        samples=list(payload.get("post_maintenance_samples") or payload.get("samples") or [])
        accepted=[]; excluded=[]
        for s in samples:
            v=self._num(s.get(metric))
            if v is None:
                excluded.append({"sample":s,"reason":"metric_invalid"}); continue
            if not s.get("baseline_eligible",True):
                excluded.append({"sample":s,"reason":"baseline_ineligible"}); continue
            if self.policy().get("require_same_operating_cluster",True):
                sp=self.peer_benchmark._cluster_parts(s)
                if any(str(sp.get(k)) != str(cluster.get(k)) for k in cluster):
                    excluded.append({"sample":s,"reason":"operating_context_mismatch"}); continue
            accepted.append({**s,metric:v})
        vals=[float(x[metric]) for x in accepted]
        after=float(median(vals)) if vals else None
        before=self._num(a.get("current_value")); peer_med=self._num(a.get("peer_median"))
        improvement=None if before in (None,0) or after is None else (before-after)/abs(before)*100
        peer_dev=None if peer_med in (None,0) or after is None else (after-peer_med)/abs(peer_med)*100
        policy=self.policy(); enough=len(vals)>=int(policy.get("minimum_verification_samples",3))
        improved=bool(improvement is not None and improvement>=float(policy.get("minimum_improvement_pct",5)))
        back_in_range=bool(peer_dev is not None and abs(peer_dev)<=float(policy.get("maximum_peer_deviation_after_pct",10)))
        case_id=str(payload.get("rca_case_id") or a.get("rca_case_id") or "")
        case=self.rca_cases.get(case_id) if case_id else None
        lifecycle_ready=bool(case and case.get("status") in {"resolved","closed"})
        verified=bool(enough and improved and back_in_range and lifecycle_ready)
        outcome={
            "outcome_id":"PBO-"+uuid.uuid4().hex[:12].upper(),"assessment_id":assessment_id,
            "rca_case_id":case_id or None,"asset_id":a.get("current_asset"),"metric":metric,
            "cluster":a.get("cluster"),"before_value":before,"after_median":None if after is None else round(after,4),
            "peer_median":peer_med,"improvement_pct":None if improvement is None else round(improvement,2),
            "deviation_vs_peer_after_pct":None if peer_dev is None else round(peer_dev,2),
            "verification_samples":len(vals),"excluded_samples":excluded[:50],"minimum_samples_met":enough,
            "improvement_target_met":improved,"returned_to_peer_range":back_in_range,"rca_lifecycle_ready":lifecycle_ready,"verified_success":verified,
            "confirmed_root_cause":(case or {}).get("confirmed_root_cause"),"resolution":(case or {}).get("resolution"),
            "policy_snapshot":policy,"verified_by":str(payload.get("actor") or "reliability_engineer"),"verified_at":_now(),
            "recommendation": "维护后效果已被同工况 Peer 验证，可沉淀为已证实案例。" if verified else ("指标已改善，但 RCA 尚未完成 resolved/closed 生命周期，暂不标记为已证实闭环。" if enough and improved and back_in_range and not lifecycle_ready else "尚未满足闭环验证条件；请补充同工况样本或复核维护动作与根因。")
        }
        self.repo.put(self.COLLECTION,outcome["outcome_id"],outcome)
        a["latest_outcome_id"]=outcome["outcome_id"]; a["outcome_verified"]=verified
        self.repo.put(self.peer_benchmark.ASSESSMENTS,assessment_id,a)
        return outcome
    def list(self,limit=200): return self.repo.list(self.COLLECTION,limit=limit)
    def get(self,outcome_id): return self.repo.get(self.COLLECTION,outcome_id)
