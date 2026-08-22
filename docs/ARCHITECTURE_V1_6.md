# V1.6 Architecture — Condition Analytics & Predictive Maintenance Integration

V1.6 closes the gap between raw IoT/SCADA time series and the V1.5 reliability decision layer.

```text
Raw IoT / Historian Time Series
            |
            v
Condition Indicator Registry
(sensor, feature, window, thresholds/baseline)
            |
            v
Deterministic Feature Engine
mean / std / RMS / slope / kurtosis / crest factor
            |
            v
Condition Indicators (0..100 risk)
            |
            v
V1.5 Reliability Intelligence
FMEA + Condition + Anomaly + Failure History
            |
            +------------------+
            v                  v
     Asset Health / Risk    RUL Adapter
            |                  |
            +--------+---------+
                     v
             Maintenance Decision
                     |
                     v
          CMMS Work-Order Candidate
                     |
              Human Approval
                     |
                     v
              CMMS Adapter/Dispatch
```

## Design boundaries

1. Feature extraction is deterministic and auditable. It does not claim ML causality.
2. Condition scores are normalized engineering indicators, not failure probabilities.
3. The built-in RUL adapter extrapolates health trend only. Production calibrated RUL models should implement the same adapter contract.
4. The platform creates a vendor-neutral CMMS contract; no work order is silently dispatched without an explicit workflow transition.
5. V1.6 reuses V1.5 `condition_indicators`, so Dynamic Risk and Asset Health remain backward compatible.

## Primary modules

- `app/condition_analytics.py`
  - `ConditionIndicatorDefinitionStore`
  - `ConditionBaselineStore`
  - `TimeSeriesFeatureEngine`
  - `ConditionAnalyticsService`
- `app/predictive_maintenance.py`
  - `RULAdapter`
  - `TrendRULAdapter`
  - `MaintenanceDecisionService`
  - `CMMSWorkOrderCandidateStore`

## Enterprise extension points

- Replace the default RUL adapter with Darts/PyTorch/ONNX/vendor models.
- Build CMMS adapters for SAP PM, IBM Maximo, Infor EAM or enterprise REST APIs.
- Populate condition definitions from an industry template and FMEA detection methods.
- Feed features from InfluxDB/Doris batch windows or an edge analytics pipeline.
