# PerfAgent AI FAQ

## What is PerfAgent AI?

PerfAgent AI is a CLI-first performance evaluation framework for microservices. It takes a service contract, generates test data and load-test artifacts, runs performance tests, extracts deterministic evidence, classifies likely bottlenecks, and produces Markdown plus interactive HTML reports.

The core principle is:

```text
Code calculates the evidence.
LLM explains the evidence.
```

## What is the current tech stack?

- Language: Python
- CLI: Typer
- Tests: pytest
- Load testing: k6
- Generated test formats: k6, Locust, JMeter
- Optional orchestration: LangGraph wrapper through `perfagent-ai[graph]`
- API parsing: OpenAPI YAML/JSON with PyYAML
- Reports: Markdown and self-contained interactive HTML
- Containers: Docker and Docker Compose
- Demo protocols: HTTP/OpenAPI, gRPC, WebSocket, UI/browser
- gRPC: grpcio, grpcio-tools, Protocol Buffers
- WebSocket demo: Python `websockets`
- Storage: filesystem artifacts
- Metrics: k6 summary JSON and k6 JSONL time-series
- Analysis: deterministic feature extraction, solo time-series analysis, cross-metric correlation, bounded ReAct-style reasoning over metric, dependency, and profiling evidence
- CI examples: GitHub Actions, GitLab CI, Jenkins

## What is implemented today?

Implemented:

- HTTP/OpenAPI end-to-end evaluation
- OpenAPI parsing
- Synthetic payload generation
- k6 script generation and execution
- k6 JSONL time-series capture
- 10-second aligned time buckets
- solo metric analysis and cross-metric correlation
- bounded ReAct-style reasoning over deterministic metric, dependency, and profiling observations
- Capacity and breakpoint extraction
- Bottleneck classification rules
- Interactive HTML report generation
- Locust and JMeter artifact generation
- gRPC/WebSocket/UI generated harness execution
- optional LangGraph workflow wrapper
- Docker Compose demo stack
- HTTP, gRPC, WebSocket, and UI demo apps
- CI examples and Make commands
- Profiling artifact attachment
- profile phase correlation with breach-overlap gated reasoning

Scaffolded but not fully active:

- LLM narrative analysis
- Prometheus saturation metrics
- distributed worker orchestration beyond merge

## Can I see flame graphs?

Yes, on Linux when `perf` is available. `profile run --mode ebpf` captures `perf.data`, converts `perf script` output into folded stacks, and writes `perf-flamegraph.svg`. The HTML report links the generated profiling artifacts and shows parsed top functions.

You can also attach existing artifacts such as Go `.pprof`, Java `.jfr`, py-spy Speedscope JSON, Clinic.js output, SVG flamegraphs, or collapsed stacks with `--profile`. The release decision still comes from SLO/time-series math, not from profile files.

## How do I run the project?

Common commands:

```bash
make setup
make test
make inspect
make run-sample
make evaluate-local
make demo-up
make evaluate-compose
make experiment-compose
```

Validate Docker Compose:

```bash
make compose-config
```

## What does `make experiment-compose` do?

It builds the PerfAgent image, starts demo services, runs PerfAgent against the HTTP demo through the Compose network, and stops the demo services.

The command is intended as the easiest containerized demo path:

```bash
make experiment-compose
```

## Which demo applications are included?

PerfAgent includes demo targets by protocol:

- HTTP/OpenAPI: `demo-http-payments` on port `8080`
- WebSocket: `demo-websocket-payments` on port `8081`
- gRPC: `demo-grpc-payments` on port `8082`
- UI/browser: `demo-ui-checkout` on port `8083`

The HTTP demo is the current end-to-end evaluation target. The other demos are ready for protocol-specific evaluator work.

## Why use OpenTelemetry Demo / Astronomy Shop later?

The OpenTelemetry Demo, also known as Astronomy Shop, is a larger CNCF ecosystem target with multiple services and realistic observability patterns. It is a good next step after the local HTTP capacity engine is reliable.

Useful links:

- https://github.com/open-telemetry/opentelemetry-demo
- https://opentelemetry.io/docs/demo/docker-deployment/

## Does PerfAgent support k6, Locust, and JMeter?

Partially.

PerfAgent currently:

- Generates and executes k6 tests.
- Generates Locust files.
- Generates JMeter `.jmx` plans.
- Provides Docker Compose services for Locust and JMeter.

PerfAgent does not yet execute Locust/JMeter through the core workflow or normalize their result files into the same feature model. That is a clear next milestone.

## How is capacity computed?

Capacity is computed from observed metrics, not guessed.

k6 emits JSONL time-series samples:

```text
raw/k6_timeseries.jsonl
```

PerfAgent buckets those samples into 10-second rows:

```text
processed/aligned_timeseries.csv
```

Then it extracts:

- `stable_rps`
- `peak_rps`
- `estimated_capacity_rps`
- `breaking_point_rps`
- `headroom_rps`
- `capacity_basis`
- `capacity_confidence`
- `capacity_limit_phase`

The implementation lives in:

- `perfagent/analyzers/alignment.py`
- `perfagent/analyzers/features.py`

## What is a breakpoint?

A breakpoint is the first observed bucket where either:

- p95 latency exceeds the configured latency SLO, or
- error rate exceeds the configured error-rate SLO.

Example:

```text
SLO p95: 500 ms
SLO error rate: 1%

baseline: 200 RPS, p95 260 ms, errors 0.2%
stress:   500 RPS, p95 780 ms, errors 2.5%

estimated capacity: 200 RPS
breaking point: 500 RPS
```

PerfAgent does not claim capacity beyond the tested range.

## How is the baseline computed?

There are two meanings today:

1. The **baseline phase** inside a single test run.
2. A future **stored golden baseline** used for regression comparison.

Today, PerfAgent computes the baseline phase from the configured strategy:

```text
warmup -> baseline -> stress -> recovery
```

Rows in `processed/aligned_timeseries.csv` are assigned to phases. Feature extraction uses those rows to detect whether baseline passed and where stress broke.

## Where is baseline data captured?

For each run:

```text
raw/k6_summary.json
raw/k6_timeseries.jsonl
processed/aligned_timeseries.csv
processed/features.json
reports/summary.json
reports/report.html
```

## How do I update a stored baseline?

There is not yet a first-class baseline command.

Manual baseline flow today:

1. Run a known-good evaluation.
2. Keep the output directory as a reference.
3. Compare future runs manually against:
   - `processed/features.json`
   - `processed/aligned_timeseries.csv`
   - `reports/summary.json`

Recommended future commands:

```bash
perfagent baseline update \
  --service-name payments-api \
  --run-dir ./outputs/payments-api-run-001 \
  --baseline-dir ./baselines/payments-api

perfagent compare \
  --run-dir ./outputs/payments-api-run-002 \
  --baseline-dir ./baselines/payments-api \
  --fail-on-regression
```

## Does PerfAgent capture golden signals?

Partially.

Captured today:

- Latency: p95, p99, max p95, max p99
- Traffic: RPS, stable RPS, peak RPS, request count
- Errors: error rate, max error rate, k6 failed request data

Scaffolded but not fully collected:

- Saturation: CPU, memory, throttling, pod restarts, queue depth, connection pool saturation

PerfAgent can now query an existing Prometheus-compatible endpoint with `--prometheus-url` and merge returned saturation metrics into `processed/aligned_timeseries.csv`. The default PromQL queries are conventional Kubernetes/service queries and may need customization for a specific environment.

## How are DB, Kafka, Redis, Cassandra, Elasticsearch, or other dependencies handled?

Declare them in config under `dependencies:` with PromQL metric mappings. PerfAgent queries those metrics, merges them into aligned time-series as `dep_<name>_<metric>` columns, writes `processed/dependency_analysis.json`, and adds a Dependency Analysis section to the report.

Optional demo dependency containers are available:

```bash
make dependencies-up
make dependencies-down
```

These services are scaffolding only. Real capacity evidence still depends on representative schemas, topics, indexes, data volume, and dependency behavior.

## What makes PerfAgent AI?

PerfAgent now supports an optional local Ollama integration. The deterministic engine calculates metrics, capacity, SLO status, dependency findings, and bottleneck classifications. When enabled, Ollama receives only that structured evidence and writes a human-readable explanation and recommendations to:

```text
processed/ai_analysis.json
reports/report.md
reports/report.html
```

Enable it with:

```bash
ollama pull llama3.2
ollama serve

.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --llm-provider ollama \
  --llm-model llama3.2
```

The LLM does not calculate p95, p99, RPS, error rate, capacity, or release decisions.

## Can PerfAgent match production traffic patterns?

Yes, for HTTP services with Prometheus route/path metrics. Use `--traffic-profile production` with `--prometheus-url` and `--prometheus-service-label`.

PerfAgent queries observed request-rate data, derives endpoint weights and production-like/peak RPS, writes `processed/traffic_profile.json`, updates `processed/test_strategy.yaml`, and generates a weighted k6 script.

Current limits:

- request payload distributions are still synthetic unless seed data is supplied
- endpoint labels must map cleanly to OpenAPI paths
- gRPC/WebSocket production profile derivation is not first-class yet

## What about Datadog, New Relic, and ELK?

PerfAgent includes traffic-profile and normalized time-series adapters for Datadog, New Relic, and Elasticsearch. Traffic-profile adapters produce the same `traffic_profile` shape used by the Prometheus path. Time-series adapters produce normalized metric rows that are merged into `aligned_timeseries.csv`.

Those providers normalize traffic and dependency samples before deterministic analysis, so strategy generation, bottleneck rules, and AI report narrative stay provider-agnostic.

Dependency metrics still depend on explicit provider-specific mappings because labels, metric names, facets, and index schemas vary by platform.

## Can PerfAgent be exposed through MCP?

Yes. The CLI/workflow engine can be wrapped as an MCP server with tools such as `evaluate_service`, `compare_regression`, `query_runs`, `validate_prometheus`, and `generate_report`. That would let IDEs, chat agents, and automation platforms drive PerfAgent through a standard protocol while the deterministic engine remains the source of truth.

## Where are golden signals stored?

Current load-side signals are stored in:

```text
raw/k6_summary.json
raw/k6_timeseries.jsonl
processed/aligned_timeseries.csv
processed/features.json
reports/summary.json
```

Future saturation signals should be merged into:

```text
processed/aligned_timeseries.csv
processed/features.json
```

## Can PerfAgent query an existing Prometheus endpoint?

Yes. Use:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --prometheus-url https://prometheus.example.com \
  --prometheus-service-label payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml \
  --output ./outputs/payments-api
```

PerfAgent calls Prometheus `/api/v1/query_range`, stores raw results in `raw/prometheus_metrics.json`, and merges matching timestamps into `processed/aligned_timeseries.csv`.

## Can users customize Prometheus labels and metric names?

Yes. Provide `--prometheus-query-config` with a YAML or JSON file:

```yaml
queries:
  cpu_percent: 'sum(rate(container_cpu_usage_seconds_total{namespace="payments", pod=~".*{service}.*"}[1m])) * 100'
  memory_mb: 'sum(container_memory_working_set_bytes{namespace="payments", pod=~".*{service}.*"}) / 1024 / 1024'
  service_request_rate: 'sum(rate(http_server_requests_seconds_count{app="{service}"}[1m]))'
  service_error_rate_percent: 'sum(rate(http_server_requests_seconds_count{app="{service}", status=~"5.."}[1m])) / sum(rate(http_server_requests_seconds_count{app="{service}"}[1m])) * 100'
```

PerfAgent replaces `{service}` with `--prometheus-service-label`. This lets users adapt to platforms that use labels like `app`, `job`, `service_name`, `namespace`, `deployment`, or custom OpenTelemetry resource labels.

## Does PerfAgent support profiling?

Yes. PerfAgent supports language-independent eBPF-style capture through Linux `perf` and can also attach existing profiling artifacts.

Example:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --profile ./profiles/cpu.pprof \
  --profile ./profiles/heap.pprof \
  --output ./outputs/payments-api
```

Artifacts are copied to:

```text
raw/profiles/
raw/profiling_artifacts.json
```

For automatic eBPF capture, use:

```bash
.venv/bin/python -m perfagent profile run \
  --runtime system \
  --mode ebpf \
  --pid 12345 \
  --duration-seconds 60 \
  --output-dir ./outputs/profiles \
  --output-json ./outputs/profiles/profile-result.json
```

PerfAgent summarizes collapsed stacks, Speedscope-style profiles, simple text profile output, and `perf script` output. See [eBPF Profiling Setup](ebpf-profiling.md).

## What does the HTML report include?

`reports/report.html` is self-contained and interactive.

It includes:

- KPI cards
- release decision
- estimated capacity
- breaking point
- max p95 latency
- max error rate
- latency/RPS chart
- breakpoint marker
- axis labels and hover tooltips
- dark/light mode toggle
- service CPU, memory, disk, and image tag metadata
- phase filter
- sortable aligned time-series table
- bottleneck evidence
- recommendations
- profiling artifact list

It embeds run data locally, so it can be uploaded as a CI artifact and opened without a backend.

## How do CI gates work?

Use `--fail-on`:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --fail-on BLOCK,UNKNOWN \
  --output ./outputs/payments-api
```

If the release decision matches one of the configured values, the command exits non-zero.

## What is missing next?

Highest-value next work:

1. Provider-specific dependency metric contracts for Datadog, New Relic, and Elasticsearch.
2. Remote/Kubernetes distributed workers with artifact upload/download and retry policy.
3. Deeper eBPF interpretation for off-CPU, allocation, runtime, and kernel evidence.
4. Browser trace parsing, waterfall summaries, and video links in the interactive report.
5. AsyncAPI-native WebSocket parsing beyond JSON Schema-style message generation.
6. gRPC reflection/protoset support for services that do not ship source `.proto` files.
7. Polished CI package with reusable GitHub Action and regression-gate examples.

## What should be prioritized next?

The strongest next milestone is:

```text
HTTP Golden Signals + Baseline Regression
```

That means:

- collect Prometheus CPU/memory/throttling
- merge saturation into aligned time-series
- persist golden baselines
- compare new runs to baseline
- fail CI on capacity regression or earlier breakpoint

This builds on the current HTTP capacity engine and makes the platform immediately useful for release gating.
