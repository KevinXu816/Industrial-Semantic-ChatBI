# V2.0 Productization Architecture

V2.0 focuses on product workflow rather than adding another analytics engine.

## Product aggregation

- `/workspace/home`: role-aware priorities for reliability engineers, maintenance planners, and operators.
- `/assets/{asset_id}/cockpit`: single-source aggregation of Asset Registry, Reliability, FMEA, RCA, CMMS, RUL, and Model Deployment.
- Cockpit now exposes health/risk history, a unified operational timeline, and Failure Mode drill-down.

## Source-of-truth rule

The product UI does not persist duplicated asset health/RCA/work-order state. It reads the existing governed domain stores and composes views at request time.

## UI workflow

Workspace → Fleet ranking → Asset cockpit → Failure Mode / timeline / RCA / maintenance context.
