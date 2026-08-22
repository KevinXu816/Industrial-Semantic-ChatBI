# V1.2 Knowledge Quality & Learning Loop Architecture

V1.2 adds a governed learning loop on top of V1.1. The central rule is that operational experience is **not automatically promoted to trusted knowledge**.

```text
Resolved RCA Case
      ↓
Knowledge Candidate
      ↓ human approval
Approved Versioned Knowledge
      ↓
Chunk Lineage / Hybrid Index
      ↓
RCA Retrieval
      ↓
Engineer Feedback
      ↓
Bounded Ranking Calibration
```

## Knowledge lifecycle

Documents support `draft`, `candidate`, `approved`, `superseded`, `retired`, and `rejected`. Default retrieval only returns approved chunks. Each chunk retains parent citation, parent provenance, version and optional source RCA case.

## Retrieval quality

`RetrievalEvaluator` executes labeled query sets and reports Recall@K and MRR. This creates an explicit quality gate for changing chunking, embeddings, lexical weights or vector backends.

## RCA reuse and calibration

`RCASimilaritySearch` searches confirmed cases using lexical and deterministic-vector similarity. `RCARankingCalibrator` derives bounded multipliers from engineer feedback; calibration adjusts evidence-based hypotheses but never creates a root cause without evidence.

## Knowledge promotion

A reviewed/resolved RCA case with a confirmed root cause can be converted to a `KnowledgeCandidate`. A knowledge approver can then promote it into versioned approved knowledge, preserving `source_case_id` provenance.

## Trust boundary

The learning loop deliberately separates:

1. **Observed evidence** — query/analytics/events.
2. **Hypotheses** — ranked RCA candidates.
3. **Human confirmation** — engineering review.
4. **Knowledge approval** — controlled promotion into reusable knowledge.

This prevents incorrect model output from automatically contaminating the enterprise knowledge base.
