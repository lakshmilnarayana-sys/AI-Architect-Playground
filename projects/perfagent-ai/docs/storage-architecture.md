# Storage Architecture

PerfAgent uses a hybrid storage model:

```text
Database stores facts.
Vector search finds related context.
AI explains both.
```

Structured storage is the source of truth for execution evidence. Vector embeddings are optional retrieval infrastructure for narratives, logs, findings, and similar-run lookup. Embeddings must never replace deterministic metrics, baselines, regression gates, or capacity calculations.

## Authoritative Storage

Use Postgres, SQLite, and object/filesystem storage for authoritative execution data.

Store structured facts in SQL:

- run metadata
- service name
- commit SHA
- image tag
- SLOs
- engine used
- p95 and p99 latency
- RPS
- error rate
- capacity
- breakpoint
- release decision
- dependency findings
- regression results
- artifact locations

Store larger artifacts in object storage or filesystem:

- raw k6 summary
- raw protocol summaries
- raw execution logs
- aligned CSV
- HTML report
- Markdown report
- profiling files
- imported Locust/JMeter files

## Vector Storage

Use vector embeddings only for semantic retrieval:

- report narrative chunks
- bottleneck explanations
- recommendations
- warnings
- execution logs, chunked
- profiling summaries
- historical incident/performance findings
- similar past regression search

Do not use embeddings for:

- p95/p99 comparison
- regression gates
- capacity calculation
- release decision
- trend analysis
- time-series math
- baseline comparison

Those must remain deterministic SQL, time-series, or file-backed calculations.

## Recommended Postgres Model

Recommended tables:

```text
perf_runs
perf_features
perf_artifacts
perf_timeseries
perf_dependencies
perf_regression_results
perf_findings
```

Optional pgvector extension:

```text
perf_embeddings
```

The `perf_embeddings` table should reference authoritative records by ID. It should not duplicate or replace the source-of-truth values.

## Table Responsibilities

`perf_runs`:

- run ID
- service name
- runtime
- engine
- target environment
- commit SHA
- image tag
- created timestamp
- release decision
- report path

`perf_features`:

- run ID
- stable RPS
- peak RPS
- p95/p99 latency
- error rate
- estimated capacity
- breaking point
- first SLO breach
- CPU/memory peaks
- recovery time

`perf_artifacts`:

- run ID
- artifact type
- path or object URI
- checksum when available
- content type
- size

`perf_timeseries`:

- run ID
- timestamp
- phase
- RPS
- p95/p99
- error rate
- virtual users
- CPU/memory/throttling
- dependency columns or linked dependency rows

`perf_dependencies`:

- run ID
- dependency name
- dependency type
- role
- metric name
- metric value
- timestamp or phase
- finding severity

`perf_regression_results`:

- current run ID
- baseline run ID
- p95 delta
- error-rate delta
- RPS delta
- regression detected
- findings JSON

`perf_findings`:

- run ID
- finding type
- severity
- evidence
- recommendation
- missing metrics
- deterministic classification or AI narrative source

`perf_embeddings`:

- embedding ID
- source table
- source ID
- chunk type
- chunk text
- embedding vector
- model name
- created timestamp

## Similar Regression Workflow

When a user asks:

```text
Have we seen this kind of p95 regression before?
```

PerfAgent should:

1. Query SQL for exact historical regressions using service name, p95 delta, error-rate delta, engine, environment, and SLO.
2. Query vector storage for semantically similar findings, logs, profiling summaries, and report narratives.
3. Join vector matches back to authoritative run IDs and artifacts.
4. Ask AI to summarize only the retrieved evidence.
5. Include links to the exact runs, reports, and metrics that support the answer.

## Retrieval Guardrails

AI may say:

- similar reports mention dependency latency
- previous findings recommended DB pool inspection
- profile summaries look similar
- missing metrics prevent confirmation

AI must not say:

- a run regressed unless SQL regression logic says so
- a service capacity changed unless deterministic features show it
- a dependency caused an issue unless dependency evidence exists
- a release should pass/block unless deterministic decision logic supports it

## MVP Position

Current MVP:

- SQLite run store
- optional Postgres run store
- filesystem artifacts
- deterministic features and reports

Recommended next storage evolution:

1. Expand Postgres schema from `perf_runs` into normalized run/feature/artifact/time-series tables.
2. Store artifact paths and checksums.
3. Add regression result persistence.
4. Add `pgvector` as an optional extension.
5. Embed only narratives, findings, warnings, logs, and profiling summaries.
6. Add a similar-regression query workflow that combines SQL filters and vector retrieval.

Current implementation includes pgvector-compatible scaffolding:

```bash
.venv/bin/python -m perfagent regression index \
  --run-dir ./outputs/sample-payments-api \
  --postgres-dsn "$PERFAGENT_DATABASE_URL"

.venv/bin/python -m perfagent regression similar \
  --query "p95 latency regression during stress with dependency timeout" \
  --postgres-dsn "$PERFAGENT_DATABASE_URL"
```

The local deterministic embedding helper is for development and tests. Production deployments should replace it with an approved embedding model while preserving the same guardrail: embeddings retrieve context, SQL stores facts.
