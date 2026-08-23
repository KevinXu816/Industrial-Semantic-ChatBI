# V3.0 Enterprise Production Release

V3.0 is a release-hardening milestone. It intentionally adds no new industrial analytics domain. It makes the existing platform deployable and operable as a production service.

## Lifecycle gates

```text
Configuration Validation
        ↓
Migration Ledger
        ↓
Startup Probe
        ↓
Readiness Probe ── external dependencies
        ↓
Traffic
        ↓
Liveness Probe ── process only
```

Liveness never depends on PostgreSQL/Doris/Qdrant. A temporary dependency outage should remove a pod from service through readiness, not trigger a restart storm.

## Production configuration

`DEPLOYMENT_ENV=production` activates fail-fast checks. Production rejects disabled authentication and JSON persistence. `EXECUTION_MODE=mock` is surfaced as a production warning.

## Migrations

Application migrations are recorded in `platform_migrations`. `AUTO_MIGRATE=true` applies idempotent V3.0 migration markers at startup. The CLI supports explicit migration for controlled deployments.

## Backup and disaster recovery

The application backup endpoint is suitable for the JSON/demo repository and for exporting production metadata manifests. PostgreSQL production recovery must use PostgreSQL-native backup: `pg_dump`/base backups and WAL archiving. V3.0 ships helper scripts but does not misrepresent an application JSON export as database DR.

## Kubernetes / HA

`deploy/kubernetes/` includes Deployment, Service, PDB, HPA and ConfigMap examples. The Deployment uses startup/readiness/liveness probes and rolling updates with `maxUnavailable: 0`. Horizontal replicas require shared PostgreSQL persistence; JSON mode is not HA-safe.

## Upgrade safety

`/production/upgrade/check` and `python -m app.production_cli upgrade-check` report configuration validity, pending migrations and major-version upgrade status. Always take and verify a backup before upgrading.
