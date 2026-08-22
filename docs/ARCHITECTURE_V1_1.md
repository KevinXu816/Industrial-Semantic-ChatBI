# V1.1 Knowledge Infrastructure Architecture

V1.1 turns governed documents and confirmed RCA cases into a reusable industrial knowledge plane while keeping the semantic query/RCA trust boundary deterministic.

```text
FMEA / SOP / Manual / Maintenance Report
                 |
                 v
        Knowledge Ingestion
       version + digest + chunk
                 |
       +---------+---------+
       |                   |
   Repository          Vector Backend
 JSON/PostgreSQL   Local/Qdrant/pgvector
       |                   |
       +---------+---------+
                 v
          Hybrid Retrieval
      lexical + vector + filter
                 |
        +--------+---------+
        |                  |
  Governed Documents  Confirmed RCA Cases
        |                  |
        +--------+---------+
                 v
          RCA Evidence Plane
                 |
      Hypothesis Ranking / Citation
```

## Core contracts

1. **Stable knowledge identity** — each document is identified by `id + version + SHA-256 digest`; each chunk has a stable content-derived `chunk_id`.
2. **Repository-first ingestion** — source documents and chunks are persisted through the V1.0 `Repository` abstraction before indexing.
3. **Pluggable retrieval** — `KNOWLEDGE_BACKEND=local|qdrant|pgvector`; RCA consumes one `search()` contract regardless of backend.
4. **Hybrid retrieval** — the zero-dependency local backend combines lexical overlap and deterministic vector similarity. Production deployments can replace the vector implementation without changing RCA orchestration.
5. **Historical RCA as knowledge** — reviewed/resolved cases with a confirmed root cause are searchable and carry `rca_case:<case_id>` provenance.
6. **Evidence, not authority** — retrieved knowledge and similar historical cases support hypothesis ranking; they do not bypass governed analytics or prove causality.

## Production recommendation

For an enterprise pilot use PostgreSQL for platform persistence and either Qdrant or pgvector for the vector index. Replace the deterministic hashing embedder with an approved enterprise embedding service while preserving document/chunk/citation identifiers.

## Optional backend installation

```bash
pip install -e '.[postgres,governance,qdrant]'
export KNOWLEDGE_BACKEND=qdrant
export QDRANT_URL=http://127.0.0.1:6333
```

or:

```bash
pip install -e '.[postgres,governance,pgvector]'
export KNOWLEDGE_BACKEND=pgvector
export DATABASE_URL=postgresql://...
```

The Enterprise Dockerfile installs PostgreSQL + governance extras by default. For a Qdrant-enabled image use `--build-arg INSTALL_EXTRAS=postgres,governance,qdrant`.
