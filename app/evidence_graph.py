"""Evidence graph for deterministic RCA traceability."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List


class EvidenceGraphBuilder:
    def _node(self, kind: str, label: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        nid = hashlib.sha1(f"{kind}:{label}".encode("utf-8")).hexdigest()[:12]
        return {"id": nid, "type": kind, "label": label, "data": data or {}}

    def build(self, plan, data: Dict[str, Any], rca: Dict[str, Any] | None = None) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, str]] = []
        by_key: Dict[tuple, str] = {}

        def add(kind: str, label: str, payload=None) -> str:
            key = (kind, label)
            if key in by_key:
                return by_key[key]
            n = self._node(kind, label, payload)
            nodes.append(n); by_key[key] = n["id"]
            return n["id"]

        subject = plan.intent.subject
        sid = add("subject", f"{subject.entity}:{subject.reference}" if subject else "subject")
        for metric in plan.intent.metrics:
            mid = add("metric", metric)
            edges.append({"from": sid, "to": mid, "relation": "MEASURED_BY"})
        for entity in plan.required_entities:
            eid = add("entity", entity)
            edges.append({"from": sid, "to": eid, "relation": "RELATED_TO"})
        for table in plan.physical_plan.get("tables", []):
            tid = add("source", table.get("table_ref", table.get("entity", "source")), table)
            eid = add("entity", table.get("entity", "entity"))
            edges.append({"from": eid, "to": tid, "relation": "MAPPED_TO"})

        rca = rca or data.get("rca") or {}
        for hyp in rca.get("hypotheses", []):
            hid = add("hypothesis", hyp.get("cause", "unknown cause"), {"confidence": hyp.get("confidence")})
            edges.append({"from": sid, "to": hid, "relation": "HAS_HYPOTHESIS"})
            for ev in hyp.get("evidence", []):
                if isinstance(ev, dict):
                    label = str(ev.get("statement") or ev.get("label") or ev)
                    payload = {k: v for k, v in ev.items() if k != "statement"}
                else:
                    label = str(ev); payload = {}
                evid = add("evidence", label, payload)
                edges.append({"from": evid, "to": hid, "relation": "SUPPORTS"})
                provenance = payload.get("provenance")
                if provenance:
                    pid = add("provenance", str(provenance))
                    edges.append({"from": pid, "to": evid, "relation": "PRODUCED"})
            for check in hyp.get("recommended_checks", []):
                cid = add("recommendation", str(check))
                edges.append({"from": hid, "to": cid, "relation": "RECOMMENDS"})
        for gh in rca.get("graph_hypotheses", []):
            gid = add("failure_mode", str(gh.get("cause", gh.get("cause_code", "failure_mode"))), {"graph_score": gh.get("graph_score"), "causal_claim_supported": gh.get("causal_claim_supported")})
            edges.append({"from": sid, "to": gid, "relation": "HAS_FAILURE_MODE"})
            for support in gh.get("supports", []):
                n = support.get("evidence_node") or {}
                eid = add(str(n.get("type", "graph_evidence")).lower(), str(n.get("label", "graph evidence")), n.get("properties") or {})
                edges.append({"from": gid, "to": eid, "relation": str(support.get("relation", "SUPPORTED_BY"))})
                if support.get("provenance"):
                    pid = add("provenance", str(support.get("provenance")))
                    edges.append({"from": pid, "to": eid, "relation": "PRODUCED"})
        analytics = rca.get("analytics", {})
        for signal in analytics.get("signals", []):
            label = f"{signal.get('type', 'signal')}:{signal.get('direction', '')}:{signal.get('magnitude_pct', signal.get('score', ''))}"
            aid = add("analytic_signal", label, signal)
            edges.append({"from": sid, "to": aid, "relation": "HAS_SIGNAL"})
        for doc in rca.get("knowledge_hits", []):
            kid = add("knowledge", str(doc.get("title", doc.get("id", "knowledge"))), {"id": doc.get("id"), "type": doc.get("type"), "score": doc.get("retrieval_score")})
            edges.append({"from": sid, "to": kid, "relation": "HAS_KNOWLEDGE"})
        temporal = rca.get("temporal_causality", {})
        previous = None
        for item in temporal.get("chain", []):
            label = f"{item.get('label','event')} ({item.get('lag_minutes',0)} min)"
            tid = add("temporal_event", label, item)
            edges.append({"from": tid, "to": sid, "relation": item.get("temporal_relation", "RELATED_IN_TIME")})
            if previous:
                edges.append({"from": previous, "to": tid, "relation": "PRECEDES"})
            previous = tid
        for corr in rca.get("sensor_correlations", []):
            if corr.get("status") == "ok":
                cid = add("sensor_correlation", f"{corr.get('sensor','sensor')} r={corr.get('correlation')}", corr)
                edges.append({"from": cid, "to": sid, "relation": "CORRELATED_WITH"})
        baseline = rca.get("operating_baseline", {})
        if baseline.get("status") == "ok":
            bid = add("operating_baseline", f"baseline deviation {baseline.get('deviation_pct')}%", baseline)
            edges.append({"from": bid, "to": sid, "relation": "COMPARES_TO"})
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges), "provenance_version": "0.9"}
