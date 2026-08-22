# V1.9 Asset Reliability Cockpit Architecture

V1.9 adds an engineer-facing aggregation layer without duplicating operational facts.

```text
Asset Registry
  ├─ hierarchy
  ├─ components
  └─ sensor bindings
        │
        ├──────────────┐
        ▼              ▼
Reliability        FMEA / Failure Model
        │              │
        ├──────┬───────┤
        ▼      ▼       ▼
      RCA    CMMS   Model Deployments
        \      |       /
         \     |      /
          Asset Reliability Cockpit
                    │
                    ▼
          Engineer / Maintenance UI
```

The Asset Registry is intentionally a master-data service. Health, risk, RCA, maintenance and model states remain owned by their original domain modules and are aggregated at read time.

## Main contracts

- `POST /assets` — create/update asset master data.
- `GET /assets/hierarchy` — governed parent/child hierarchy.
- `POST /assets/{id}/components` — component registry.
- `POST /assets/{id}/sensors` — sensor binding.
- `GET /assets/{id}/cockpit` — aggregated asset reliability context.
- `GET /reliability/fleet` — latest fleet-level risk ranking.
