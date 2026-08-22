"""Runtime query telemetry persisted through the Enterprise repository."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from .persistence import Repository
class RuntimeQueryStore:
    COLLECTION="runtime_queries"
    def __init__(self,repo:Repository): self.repo=repo
    def record(self,payload:Dict[str,Any]):
        rid=payload.get("query_id") or str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
        rec={"query_id":rid,"created_at":now,**payload}; self.repo.put(self.COLLECTION,rid,rec); return rec
    def recent(self,limit=100): return self.repo.list(self.COLLECTION,limit)
    def summary(self):
        rows=self.repo.list(self.COLLECTION,1000); n=len(rows); successful=[r for r in rows if r.get("success") is True]
        durations=[float(r.get("duration_ms",0)) for r in rows if r.get("duration_ms") is not None]
        costs=[float(r.get("normalized_cost",0)) for r in rows if r.get("normalized_cost") is not None]
        return {"total":n,"success_rate":round(len(successful)/max(1,n),3),"avg_duration_ms":round(sum(durations)/max(1,len(durations)),2),
                "avg_normalized_cost":round(sum(costs)/max(1,len(costs)),2)}
