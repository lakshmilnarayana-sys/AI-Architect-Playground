# Performance Auto-Validation Questionnaire

Use this checklist before expecting PerfAgent to make a deterministic performance decision. The framework can only validate what is explicitly defined, measurable, and aligned to a test window.

## Minimum Required Inputs

These inputs are required for deterministic output.

| Input | Required value | Why it is needed | Deterministic artifact |
| --- | --- | --- | --- |
| Service name | Stable service identifier, for example `payments-api` | Groups runs, baselines, reports, and regression history | `summary.json.service_name`, run store rows |
| API contract | OpenAPI file for HTTP, proto/service config for gRPC, WebSocket scenario config, or UI journey config | Defines what traffic is generated and which requests are covered | `contract_analysis.json`, generated scripts |
| Target URL | Reachable endpoint from the load generator | Defines where tests execute | execution log, generated scripts |
| Runtime | `go`, `java`, `python`, `node`, etc. | Used for report context and future profiling/runtime rules | `summary.json.runtime` |
| SLO p95 latency | Numeric milliseconds, for example `500` | Defines pass/fail latency threshold | `features.json.slo_p95_latency_ms` |
| SLO error rate | Numeric percent, for example `1` | Defines pass/fail error threshold | `features.json.slo_error_rate_percent` |
| Test duration | Explicit duration, for example `10m` | Defines observation window | `test_strategy.yaml`, aligned rows |
| Engine | `k6`, `grpc`, `websocket`, `ui`, `locust`, or `jmeter` | Determines execution and parser path | generated engine artifact, summary |
| Output directory | Writable path | Stores reproducible evidence | `raw/`, `processed/`, `reports/`, `state/` |

Without these inputs PerfAgent can generate partial artifacts, but the release decision should be treated as `UNKNOWN`.

## Capacity And Breakpoint Inputs

These inputs are required if users want to answer: "How much load can this service handle, and where does it break?"

| Input | Required value | Why it is needed | Deterministic output |
| --- | --- | --- | --- |
| Load model | Fixed stages or capacity mode | Determines how offered load increases | `test_strategy.yaml` |
| Baseline load | Expected steady traffic, for example `200 RPS` | Separates normal-load failure from stress-only failure | release decision `PASS/WARN/BLOCK` |
| Stress load | Peak or above-peak target, for example `500 RPS` | Exposes breakpoint/headroom | `breaking_point_rps`, `estimated_capacity_rps` |
| Warmup window | Duration before baseline | Avoids cold-start bias | phase summaries |
| Recovery window | Duration after stress | Validates whether service returns to SLO | `recovery.status`, `recovery_time_seconds` |
| Step size | RPS increments or stage targets | Controls breakpoint precision | capacity confidence |
| Minimum stable window | Number of buckets considered stable | Avoids single-bucket false capacity | `stable_rps`, capacity basis |

Deterministic capacity output requires aligned time buckets with at least `rps`, `p95_latency_ms`, and `error_rate_percent`.

## Golden Signal Checklist

PerfAgent can reason with only load-test metrics, but confidence improves when all four golden signals are present.

| Signal | Metric examples | Required for | Missing-metric impact |
| --- | --- | --- | --- |
| Latency | `p95_latency_ms`, `p99_latency_ms`, service p95/p99 | SLO breach, breakpoint, regression | Cannot validate latency SLO |
| Traffic | `rps`, request rate, endpoint mix | Capacity and production-like replay | Cannot estimate capacity reliably |
| Errors | `error_rate_percent`, 5xx rate, failed checks | SLO breach and instability | Cannot validate error SLO |
| Saturation | CPU, memory, throttling, queue depth, pool usage | Bottleneck classification | Root cause confidence drops |

Minimum deterministic validation:

- `rps`
- `p95_latency_ms`
- `error_rate_percent`

Recommended deterministic diagnosis:

- `rps`
- `p95_latency_ms`
- `p99_latency_ms`
- `error_rate_percent`
- `virtual_users`
- `cpu_percent`
- `memory_mb`
- `cpu_throttling_percent`
- dependency latency or queue/pool metrics

## Observability Inputs

Provide these when PerfAgent should compare test behavior against production-like traffic or correlate bottlenecks.

| Input | Example | Why it matters |
| --- | --- | --- |
| Metrics provider | Prometheus, Datadog, New Relic, Elasticsearch | Selects query adapter |
| Query endpoint | `http://prometheus:9090` | Allows live metric collection |
| Service label mapping | `service`, `app`, `job`, `namespace`, `pod` | Real platforms use different label names |
| Endpoint label mapping | `route`, `path`, `http_route`, `uri_template` | Required for endpoint traffic mix |
| Request rate query | PromQL or provider query | Builds production-like load stages |
| Latency query | p95/p99 query | Compares service-side latency with client-side load-test latency |
| Error query | 5xx/error-rate query | Correlates failures |
| Infra queries | CPU, memory, throttling, restarts | Classifies saturation |
| Time range | Lookback such as `6h`, `24h`, `7d` | Defines production sample window |

If labels are unknown, run:

```bash
perfagent prometheus validate \
  --prometheus-url http://localhost:9090 \
  --prometheus-service-label payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml
```

## Dependency Checklist

Declare dependencies when the service talks to databases, queues, caches, search clusters, or external APIs.

| Dependency | Metrics needed for deterministic reasoning |
| --- | --- |
| Postgres/MySQL | query p95, connection pool utilization, active connections, lock waits, slow queries |
| Redis | command p95, memory usage, evictions, hit ratio, blocked clients |
| Kafka | consumer lag, produce latency, fetch latency, broker request queue, under-replicated partitions |
| Cassandra | read/write p95, pending compactions, tombstones, timeouts, coordinator errors |
| Elasticsearch/OpenSearch | search p95, indexing latency, rejected threads, heap pressure, queue size |
| External HTTP APIs | dependency p95/p99, timeout count, retry count, circuit breaker state |

Each dependency should include:

- name
- type
- upstream or downstream role
- criticality
- query per metric
- threshold per metric when known

Without dependency metrics, PerfAgent may correctly say latency breached SLO, but root cause confidence should remain `low` or `medium`.

## Baseline And Regression Checklist

Provide these for deterministic regression gates.

| Input | Required value | Deterministic output |
| --- | --- | --- |
| Baseline run | Stored previous passing run for the same service | `baseline_run_id` |
| Current run | New run summary | regression comparison |
| Commit SHA | Current code revision | traceability |
| Image tag | Container image under test | reproducibility |
| Environment | CI, staging, perf, local | prevents invalid comparisons |
| Regression thresholds | p95 delta %, error-rate delta %, capacity delta % | pass/fail gate |
| Retention | Default `30 days` or configured | historical query window |

Do not use vector embeddings for regression gates. Regression gates must use structured values from SQL/time-series data.

## Profiling Checklist

Profiling is needed when PerfAgent must explain why saturation occurs.

| Runtime | Recommended profiling artifacts |
| --- | --- |
| Go | CPU profile, heap profile, goroutine profile, block/mutex profile |
| Java | JFR, GC logs, thread dumps, heap histograms |
| Python | py-spy CPU profile, memory snapshots, async task dumps |
| Node.js | CPU profile, heap snapshot, event loop delay |
| Container/Kubernetes | cgroup CPU throttling, memory working set, OOM events, restart count |

Profiling artifacts are supporting evidence. They should not replace time-series metrics for release decisions.

## UI And Browser Checklist

For UI performance validation, provide:

- URL path
- wait selector
- action selector or journey steps
- expected success selector or response
- browser type
- concurrency
- think time
- Web Vitals targets if known

Recommended deterministic browser metrics:

- DOM content loaded
- load event time
- first paint
- first contentful paint
- transfer size
- request failure count

## Required Output Review

A run is suitable for automated validation only if these files exist:

- `raw/k6_summary.json` or engine-specific summary
- `raw/execution_result.json`
- `processed/aligned_timeseries.csv`
- `processed/features.json`
- `processed/timeseries_analysis.json`
- `processed/react_reasoning.json`
- `processed/bottleneck_analysis.json`
- `reports/summary.json`
- `reports/report.html`

## Decision Rules

PerfAgent should emit:

- `PASS`: baseline and stress stay within latency/error SLOs, no severe saturation.
- `WARN`: baseline passes but stress breaches SLO, indicating limited headroom.
- `BLOCK`: baseline breaches SLO, expected-load error rate is too high, or service is unstable.
- `UNKNOWN`: execution failed, required metrics are missing, or evidence is insufficient.

## Confidence Rules

| Confidence | Required evidence |
| --- | --- |
| High | SLO breach plus strong correlated saturation/dependency signal and sufficient recovery window |
| Medium | SLO breach plus partial correlation or deterministic breakpoint without root-cause metric |
| Low | Missing core metrics, only summary data, no aligned time-series, or no dependency/infra visibility |

## Exact Questions For Service Owners

1. What service name should be used consistently in reports, metrics, and CI?
2. What protocol is being tested: HTTP, gRPC, WebSocket, UI/browser, or mixed?
3. Where is the contract: OpenAPI, proto file, WebSocket message schema, or UI journey config?
4. What target URL should the load generator use from CI or the test network?
5. What is the expected baseline RPS?
6. What is the expected peak RPS?
7. What p95 latency SLO should gate the release?
8. What error-rate SLO should gate the release?
9. How long should warmup, baseline, stress, and recovery phases run?
10. What is the minimum acceptable capacity/headroom?
11. Which environment is authoritative for validation: local, CI, staging, perf, or pre-prod?
12. What image tag, commit SHA, and runtime version are under test?
13. Which metrics provider should PerfAgent query?
14. What labels identify this service in metrics?
15. What label identifies HTTP route or endpoint in metrics?
16. Which dependencies are in the critical path?
17. What dependency metrics and thresholds are available?
18. Are CPU, memory, throttling, and restart metrics available for the service under test?
19. Should production traffic shape be queried and replayed?
20. What baseline run should the current run compare against?
21. What regression thresholds should fail CI?
22. What profiling artifacts should be attached when a bottleneck is detected?
23. Should the final report be stored, commented on a PR, or published as a CI artifact?

## Deterministic Validation Contract

PerfAgent can auto-validate performance characteristics when this contract is satisfied:

```yaml
service:
  name: payments-api
  runtime: go
  image_tag: payments-api:1.2.3
  commit_sha: abc123
contract:
  type: openapi
  path: ./openapi.yaml
target:
  url: http://payments-api:8080
slo:
  p95_latency_ms: 500
  error_rate_percent: 1
load:
  baseline_rps: 200
  stress_rps: 500
  warmup_duration: 2m
  baseline_duration: 5m
  stress_duration: 5m
  recovery_duration: 2m
metrics:
  required:
    - rps
    - p95_latency_ms
    - error_rate_percent
  recommended:
    - p99_latency_ms
    - cpu_percent
    - memory_mb
    - cpu_throttling_percent
dependencies:
  postgres:
    type: postgres
    role: downstream
    metrics:
      p95_latency_ms: promql_or_provider_query
      connection_pool_utilization_percent: promql_or_provider_query
regression:
  baseline_run_id: latest_pass
  max_p95_regression_percent: 20
  max_error_rate_delta_percent: 0.5
```
