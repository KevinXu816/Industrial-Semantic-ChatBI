# V1.5 Architecture — Reliability Intelligence & Predictive Maintenance

V1.5 connects governed static FMEA risk to runtime condition evidence.

```text
Approved FMEA (S/O/D/RPN)
        +
FailureMode ↔ Sensor Mapping
        +
Condition Indicators / Anomaly / Failure History
        ↓
Explainable Dynamic Risk Model
        ↓
FailureMode Risk Ranking
        ↓
Asset Health Score + Trend
        ↓
Maintenance Priority + Inspection Recommendation
```

The dynamic score is a transparent weighted decision-support indicator: 40% static FMEA, 30% condition, 15% anomaly, 15% failure history. It is deliberately not exposed as a calibrated probability of failure. Assessments and mappings use the existing Repository abstraction and therefore work with JSON or PostgreSQL.
