# V1.4 Industrial Failure Model & FMEA Studio

V1.4 promotes reliability engineering data to a first-class governed domain model. FMEA records are persisted independently from generic RAG documents and only approved records are projected into the Industrial Knowledge Graph.

## Architecture

```text
Asset
  └─ HAS_COMPONENT → Component
       └─ HAS_FAILURE_MODE → FailureMode
            ├─ CAUSED_BY → FailureCause
            ├─ HAS_EFFECT → FailureEffect
            ├─ DETECTED_BY → DetectionMethod
            ├─ INDICATED_BY → Alarm
            └─ RESOLVED_BY → MaintenanceAction
```

Each FMEA record contains Severity, Occurrence and Detectability scores in the range 1..10. `RPN = S × O × D`. V1.4 also derives a conservative default criticality class. Severity >= 9 is always treated as critical even if RPN is lower; enterprises should externalize these thresholds before production rollout.

## Governance boundary

FMEA lifecycle is `draft/candidate → approved → retired`. Draft or candidate FMEA records do not enter the graph. Approval writes graph provenance in the form `fmea:<fmea_id>@<version>`.

## APIs

- `POST /fmea`
- `GET /fmea`
- `GET /fmea/{fmea_id}`
- `PUT /fmea/{fmea_id}`
- `POST /fmea/{fmea_id}/approve`
- `POST /fmea/{fmea_id}/retire`
- `GET /fmea/risk-ranking`

## Product role

V1.4 joins Semantic Intelligence, RCA and Reliability Engineering. The same governed FailureMode can now be supported by FMEA design knowledge, runtime evidence, historical RCA cases and maintenance actions while preserving provenance.
