# V2.1 Reliability Workflow UX

V2.1 keeps the V2.0 domain services as sources of truth and adds a product workflow layer for day-to-day reliability engineering.

## Product flow

```text
Plant / Line / Asset Tree
        ↓
Asset Reliability Cockpit
        ↓
7d / 30d / 90d Health & Risk Trend
        ↓
Failure Mode Drill-down
        ↓
RCA Case Workflow
Open → Analyze → Evidence Review → Engineer Confirm → Resolve → Close
        ↓
Maintenance / CMMS linkage
```

## Architecture principles

- Asset hierarchy remains in `AssetRegistry`; operational health is not copied into asset master data.
- Cockpit time-range filtering is a read/presentation concern over governed reliability history.
- `RCAWorkflowService` aggregates RCA cases, hypotheses, evidence and related CMMS candidates without duplicating their state.
- RCA closure is explicit and permitted only after resolution.
- UI version continues to come from `/health` and `app/version.py`.

## New APIs

- `GET /rca/workflows`
- `GET /rca/cases/{case_id}/workflow`
- `POST /rca/cases/{case_id}/close`
- `GET /assets/{asset_id}/cockpit?days=7|30|90`

## Front-end additions

- Plant → Line → Asset tree browser.
- 7/30/90 day time-range selector.
- SVG Health and Dynamic Risk trend chart.
- Dedicated RCA Workflow screen with workflow stages, hypotheses, evidence review, maintenance linkage, engineer confirm, resolve and close operations.
