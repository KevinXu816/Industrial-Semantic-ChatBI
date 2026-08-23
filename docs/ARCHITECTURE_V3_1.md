# V3.1 Enterprise Pilot Pack

V3.1 deliberately stops broad platform expansion and packages a customer-validation scenario: **air-compressor specific-energy anomaly + predictive maintenance**.

## Pilot flow

1. Bootstrap `F01 → LINE-01 → A101` and governed Filter Restriction FMEA.
2. Bind/ingest IoT energy & condition data, MES production output and CMMS events using existing V2.x integration contracts.
3. Compute specific-energy and condition indicators.
4. Run reliability/RCA and expose evidence to an engineer.
5. Record post-repair operational KPI measurements.
6. Make a GO/NO-GO decision from measurable acceptance criteria.

The pilot layer does not duplicate Asset, FMEA, Reliability or RCA sources of truth. It orchestrates those existing services and stores only pilot run/KPI metadata.
