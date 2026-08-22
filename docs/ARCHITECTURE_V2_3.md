# V2.3 Integration Runtime & Data Quality

V2.3 adds a governed integration runtime control plane above V2.2 Data Binding. Vendor adapters still fetch data; the platform owns schedule metadata, incremental watermarks, schema fingerprints/drift policy, data-quality rules, retry/dead-letter state and monitoring.

Core flow: Adapter -> Approved Binding -> Schema Gate -> Watermark Gate -> Data Quality -> Domain Write -> Run/Audit/DLQ.

This avoids embedding vendor-specific networking in the platform core while making long-running integrations observable and safe.
