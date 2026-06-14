# Capacity, Regression, And CI

## Capacity Definition

Capacity is the highest observed load level the service sustained while meeting the configured SLOs.

Breaking point is the first load level where the service breaches latency or error SLO.

Headroom is the difference between expected/production-like load and estimated capacity.

Do not report capacity without:

- SLO values used
- phase or RPS where first breach occurred
- max p95 and max error rate
- number of samples or duration per phase
- confidence level
- missing metrics

## Capacity Confidence

High:
- multi-stage capacity run completed
- clear sustained SLO breach
- aligned load, service, infra, and dependency metrics
- recovery observed

Medium:
- load-side metrics and partial service metrics exist
- breach is clear, but dependency or saturation data is incomplete

Low:
- only one load-side summary exists
- no service/infra metrics
- test duration is very short
- target service was unreachable

## Baseline Handling

Baseline is a known-good run for a specific service, environment, config, and workload.

Store or compare:

```bash
.venv/bin/python -m perfagent baseline save \
  --run-dir ./outputs/payments-api \
  --baseline-dir ./baselines

.venv/bin/python -m perfagent baseline compare \
  --run-dir ./outputs/payments-api \
  --baseline-dir ./baselines
```

Database-backed regression:

```bash
.venv/bin/python -m perfagent regression compare \
  --run-dir ./outputs/payments-api \
  --db-path ./outputs/perfagent.db \
  --max-p95-regression-percent 20 \
  --max-error-rate-delta-percent 0.5 \
  --fail-on-regression
```

Do not compare:

- different environments
- different workloads
- different SLOs
- different test durations
- different dependency state
- cold cache vs warm cache unless intended

## Run Store

Default local store:

```yaml
storage:
  enabled: true
  backend: sqlite
  path: ./outputs/perfagent.db
  retention_days: 30
```

Shared CI store:

```yaml
storage:
  enabled: true
  backend: postgres
  dsn_env: PERFAGENT_DATABASE_URL
  retention_days: 30
```

Run metadata should include:

- run ID
- service name
- created timestamp
- release decision
- stable RPS
- max p95 latency
- max error rate
- report path
- features JSON
- summary JSON

## Structured Storage Versus Embeddings

Use SQL/object storage for facts:

- run metadata
- service name, commit SHA, image tag
- SLOs
- engine used
- p95, p99, RPS, error rate
- capacity, breakpoint, release decision
- aligned time-series
- dependency metrics
- raw summaries
- report artifacts

Use vector embeddings only for semantic retrieval:

- report narratives
- bottleneck explanations
- recommendations
- warnings
- execution logs, chunked
- profiling summaries
- historical incident/performance findings
- similar past regression search

Never use embeddings for p95/p99 comparison, regression gates, capacity calculation, release decision, trend analysis, time-series math, or baseline comparison.

Recommended future Postgres schema:

```text
perf_runs
perf_features
perf_artifacts
perf_timeseries
perf_dependencies
perf_regression_results
perf_findings
perf_embeddings  # optional pgvector extension
```

For similar-regression search, query SQL first for exact regressions, then vector search for related narratives/log findings, then let AI summarize retrieved evidence.

## Continuous Performance

PR runs:
- Run smoke for docs/low-risk changes.
- Run targeted tests for service code changes.
- Run full capacity/regression for database, dependency, infrastructure, runtime, or high-risk changes.

Nightly:
- Run production-like traffic profile.
- Compare against latest baseline/history.

Weekly:
- Run full capacity mode.
- Include dependency and saturation metrics.
- Save a fresh baseline only after review.

## PR Complexity Mapping

Smoke:
- docs
- comments
- low-risk static files

Targeted:
- service code
- API handlers
- schemas/contracts
- generated clients

Full regression:
- DB migrations
- Kafka topic/schema changes
- Redis/cache behavior changes
- dependency versions
- runtime or container changes
- Kubernetes resource changes
- autoscaling changes
- authentication/session changes
- cross-service contract changes

## GitHub Actions Pattern

Core steps:

1. Start dependencies and service.
2. Run PerfAgent.
3. Run regression compare.
4. Upload `outputs/**`.
5. Comment PR with summary.
6. Fail on `BLOCK`, `UNKNOWN`, or regression based on policy.

PR comment should include:

- service name
- release decision
- stable RPS
- max p95
- max error rate
- regression detected
- findings
- artifact link

## Retention

Default retention is 30 days. Make it configurable per repository/team.

Keep longer retention for:

- weekly full capacity baselines
- release-candidate benchmarks
- major architecture comparisons

Prune:

```bash
.venv/bin/python -m perfagent storage retention \
  --db-path ./outputs/perfagent.db \
  --retention-days 30
```
