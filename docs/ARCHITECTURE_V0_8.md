# Architecture V0.8 — Industrial RCA Intelligence

V0.8 keeps V0.7's governed semantic query path and adds an evidence-first RCA plane.

```text
Question / SemanticIntent
        |
        v
RBAC/RLS/Column Policy
        |
        v
Semantic Planner -> Doris Physical Plan -> SQL Gateway -> Doris
        |                                      |
        |                                      +-> EXPLAIN Cost Adapter
        v
Evidence Dataset
        |
        +-> Time-Series Analytics (trend / robust anomaly / change-point)
        +-> Alarm + WorkOrder Correlation
        +-> Governed Knowledge Retrieval (FMEA / SOP / Manual)
        |
        v
Hypothesis Ranker
        |
        v
Evidence Graph (Evidence -> Hypothesis -> Recommendation + Provenance)
```

## Design principles

1. The LLM does not manufacture evidence. Deterministic analytics and governed retrieval create evidence first.
2. Every hypothesis carries provenance references back to query output, AlarmEvent, WorkOrder, or a knowledge document.
3. Knowledge retrieval is adapter-based. V0.8 ships a deterministic local retriever; Qdrant/Azure AI Search/pgvector can replace it later without changing the RCA contract.
4. Doris EXPLAIN is optional. Mock mode uses a logical cost estimate; live Doris mode can parse EXPLAIN output.

## New modules

- `timeseries_analytics.py`: trend, median/MAD robust anomaly, simple two-segment level shift.
- `event_correlation.py`: correlates analytical signals with alarms/work orders.
- `knowledge.py`: governed local knowledge retrieval interface.
- `hypothesis_ranker.py`: evidence-weighted RCA ranking.
- `doris_explain.py`: Doris EXPLAIN parsing and normalized cost estimation.
- `evidence_graph.py`: provenance nodes and analytic/knowledge evidence links.

## V0.9 direction

Move persistence from JSON/YAML to PostgreSQL, add production Qdrant/Azure AI Search adapters, real event-time correlation windows, FMEA ontology entities, Doris runtime statistics feedback, and human RCA review/learning.
