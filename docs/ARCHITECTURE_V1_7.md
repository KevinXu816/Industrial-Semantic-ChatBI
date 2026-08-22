# V1.7 Architecture — Condition Model Templates, Feature Pipelines & Model Registry

V1.7 turns the V1.6 condition/predictive-maintenance capabilities into a governed model platform rather than a collection of individual APIs.

```text
Asset Type / Failure Mode
        ↓
Condition Model Template
        ↓
Indicator Definitions
        ↓
Feature Pipeline Job
        ↓
Raw IoT / Historian Window
        ↓
Condition Features / Risk Indicators
        ↓
Reliability Assessment
        ↓
Governed Model Registry
        ↓
Prediction / RUL Adapter
        ↓
Maintenance Decision / CMMS Contract
```

## Condition model templates

Built-in templates are provided for `bearing`, `pump`, `compressor`, `motor`, `fan`, `pcs`, and `battery`. A template declares recommended sensors and governed feature definitions. Applying a template creates ordinary V1.6 Condition Indicator Definitions; downstream reliability APIs therefore remain unchanged.

## Feature pipeline

`FeaturePipelineStore` persists jobs and executions. V1.7 implements an on-demand execution contract over supplied time-series windows. It deliberately does not pretend to be a scheduler: Airflow, Dagster, cron, Kafka/Flink, or an industrial IoT orchestration layer can invoke the same run endpoint later.

## Model registry

`PredictiveModelRegistry` governs model identity, version, status, input/output contracts, artifact URI and inference runs. Only `approved` models can execute. `rule` and transparent statistical reference models execute locally. `darts`, `onnx`, and `external` entries expose an adapter-required contract rather than silently loading arbitrary artifacts.

This keeps model governance separate from model runtime and prevents an unapproved model version from influencing maintenance decisions.
