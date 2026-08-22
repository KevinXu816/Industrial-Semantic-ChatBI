# V2.2 Industrial Data Binding & Integration Studio

V2.2 moves productization from UI workflow to repeatable customer data onboarding.

## Architecture

External systems (InfluxDB, historian, MES, CMMS, Doris/MySQL/PostgreSQL, API/MQTT/CSV) remain behind adapters/collectors. The core platform owns a governed mapping contract:

Source records → Data Binding → normalized domain contract → existing source-of-truth service.

Supported normalized targets: Asset, Sensor Binding, Condition Series, Alarm, Work Order.

## Governance

Bindings are created as `draft`. Preview is read-only. Only `approved` bindings may execute. Every execution creates a run record with counts, errors, actor and timestamp. This prevents an unreviewed mapping from silently contaminating Asset/CMMS master data.

## Integration boundary

V2.2 intentionally does not embed every vendor protocol in the domain layer. A customer adapter/collector fetches data and invokes the approved binding. This keeps vendor-specific authentication, query dialects and polling outside reliability domain services.
