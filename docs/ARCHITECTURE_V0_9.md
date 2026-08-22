# V0.9 Architecture — Production RCA Analytics

V0.9 turns the V0.8 evidence-first RCA prototype into a more production-oriented diagnostic pipeline. It does **not** claim statistical causality from correlation. Instead it creates auditable temporal and operating-condition evidence that can support or weaken RCA hypotheses.

## RCA execution plane

```text
Metric / anomaly anchor T0
          |
          +--> deterministic time-series signals
          |
          +--> TemporalCausalityEngine
          |      T0-30m sensor signal
          |      T0-10m alarm
          |      T0+05m work-order/event
          |
          +--> SensorCorrelationEngine
          |      driver series --lag--> target series
          |
          +--> OperatingBaselineEngine
          |      current condition vs comparable baseline
          |
          +--> EventCorrelationEngine
          |
          +--> Versioned KnowledgeRetriever
          |      FMEA / SOP / Manual + citation + digest
          |
          +--> HypothesisRanker
          |
          +--> EvidenceGraph + Provenance
          |
          +--> Human RCA Review / Feedback
```

## Design principles

1. Temporal precedence is evidence, not automatic proof of causality.
2. Sensor lag correlation is deterministic and traceable; the returned lag is in sample points because sampling cadence is datasource-specific.
3. Operating baselines compare like-for-like operating regimes when the caller supplies a governed baseline cohort.
4. Knowledge evidence is versioned using `document_id@version#digest`, so an RCA case can state exactly which FMEA/SOP/manual revision supported the conclusion.
5. Human review is append-only. It can later be used to calibrate hypothesis weights without overwriting historical RCA evidence.

## New API surface

- `POST /rca/temporal-chain`
- `POST /rca/sensor-correlation`
- `POST /rca/baseline`
- `POST /rca/feedback`
- `GET /rca/feedback`

Existing `/rca/analyze`, `/analytics/timeseries`, `/knowledge/search`, semantic planning and V0.7 governance APIs remain compatible.

## Next production step

V1.0 should replace file persistence with PostgreSQL, add a vector-search adapter (Qdrant/Azure AI Search/pgvector), persist RCA cases/evidence graphs, bind sensor lag to real sampling intervals, add governed operating-regime segmentation, and connect Doris EXPLAIN/runtime statistics to admission control.
