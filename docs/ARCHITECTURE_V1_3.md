# V1.3 Architecture — Industrial Knowledge Graph & Causal Model

V1.3 adds a governed graph reasoning layer above the V1.2 semantic, knowledge and RCA platform.

```text
Approved FMEA / SOP / Manual ─┐
Confirmed RCA Case ───────────┼──> Graph Ingestion
Ontology / runtime evidence ──┘        │
                                      ▼
                         Industrial Knowledge Graph
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
        FailureMode                Component                 Alarm
             │                        │                        │
          CAUSED_BY                PART_OF                INDICATED_BY
             │                                                 │
             ├──── DETECTED_BY ── SensorPattern                 │
             └──── RESOLVED_BY ── MaintenanceAction             │
                                      │
                                      ▼
                           CausalGraphReasoner
                                      │
                         Graph hypothesis + support
                                      │
                                      ▼
                         Existing RCA evidence ranker
```

## Trust semantics

V1.3 deliberately separates governed causal knowledge from observational evidence.

- `CAUSED_BY`, `RESOLVED_BY`: strong governed causal/operational relations. They should originate from approved FMEA/SOP or confirmed RCA evidence.
- `INDICATED_BY`, `DETECTED_BY`, `SUPPORTED_BY`: diagnostic evidence relations.
- `CORRELATED_WITH`, `PRECEDES`: observational relations. They are evidence, not causal proof.

The reasoner returns `causal_claim_supported` so a client can distinguish a causal path backed by governed knowledge from a merely correlated hypothesis.

## Persistence

The graph uses the V1.0 Repository contract (`industrial_graph_nodes`, `industrial_graph_edges`). It therefore works with the zero-configuration JSON repository and the PostgreSQL enterprise backend without coupling graph logic to a database vendor.

## Automatic graph promotion

Only approved knowledge is promoted. Candidate/draft knowledge is ignored. Resolving an RCA case with a confirmed root cause also adds case evidence to the graph. This keeps the graph downstream of the V1.2 governance workflow rather than creating an ungoverned parallel knowledge store.
