# V1.0 Enterprise Pilot Architecture

V1.0 freezes the V0.9 semantic/RCA contracts and adds an enterprise operations plane.

```text
Industrial Copilot / RCA UI
          |
          v
Semantic + RCA APIs
          |
   +------+-------+
   |              |
Governed Query   RCA Case Management
   |              |
Doris           Evidence / Review / Resolution
   |              |
MES/EMS/...     Repository API
                  |
          JSON (demo) / PostgreSQL (pilot)
```

## Key design decisions

1. **Repository abstraction**: JSON remains the zero-dependency default; PostgreSQL is selected through `PERSISTENCE_BACKEND=postgres`.
2. **RCA is a case lifecycle**: `open -> analyzed -> reviewed -> resolved -> closed`, with append-only history.
3. **Human review is first-class**: confirmed root cause and resolution are persisted beside model hypotheses.
4. **Runtime telemetry is durable**: governed query runtime, user/roles, catalogs, latency and normalized cost can be inspected through operations APIs.
5. **No LLM in the execution trust boundary**: SemanticIntent, ontology paths, metric graph, governance and SQL guardrails remain deterministic.

## Pilot deployment

`docker-compose.enterprise.yml` starts the API and PostgreSQL. Production deployments should externalize secrets, enable TLS, configure Doris, and place the API behind the enterprise identity gateway.
