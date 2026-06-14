# PerfAgent AI

From API contract to performance report using deterministic analysis and agent-ready workflows.

PerfAgent AI is a CLI-first performance evaluation framework for microservices. It accepts an API contract and SLOs, generates synthetic test data and load-test artifacts, runs the selected test engine, extracts performance evidence, reasons across aligned time-series metrics, classifies likely bottlenecks, and writes Markdown/HTML reports.

The design principle is:

```text
Code calculates the evidence.
LLM explains the evidence.
```

The current MVP supports HTTP/OpenAPI end to end and includes first-class generated harnesses for gRPC, WebSocket, and UI/browser demo runs. k6 remains the primary HTTP engine; Locust and JMeter artifacts are generated for external execution/import.

## What Works Now

- Parse OpenAPI YAML/JSON contracts
- Extract endpoints, methods, request bodies, required headers, path parameters, query parameters, and expected status codes
- Generate deterministic non-PII synthetic payloads
- Generate runnable k6 JavaScript
- Run k6 natively, or fall back to `grafana/k6:latest` through Docker when native k6 is unavailable
- Capture k6 summary output and execution logs
- Generate aligned time-series CSV scaffold
- Analyze each time-series metric independently and correlate load, latency, errors, infra, browser, and dependency metrics
- Produce an auditable bounded ReAct-style reasoning trace from deterministic metric-tool observations
- Extract p95, p99, RPS, error rate, request count, first SLO breach, and release decision
- Classify bottlenecks using deterministic rules
- Generate `report.md`, `report.html`, `summary.json`, `features.json`, and `metric_contract.yaml`
- Generate a self-contained interactive `report.html` with KPI cards, capacity/breakpoint chart, autonomous reasoning trace, phase filtering, and a sortable time-series table
- Run the framework and demo services with Docker Compose
- Optionally run the evaluation through a LangGraph wrapper with `--workflow langgraph`

## Repository Layout

```text
perfagent-ai/
├── perfagent/                  # CLI, workflow, agents, analyzers, generators
├── examples/
│   ├── sample-openapi.yaml
│   ├── sample-payments-api/    # HTTP/OpenAPI demo service
│   └── demo-apps/
│       ├── websocket-payments-api/
│       └── grpc-payments-api/
├── tests/
├── docs/
│   └── demo-applications.md
├── Dockerfile                  # PerfAgent image with k6 bundled
├── docker-compose.yml          # PerfAgent plus demo services
└── pyproject.toml
```

## Common Commands

The easiest way to work with the project is through `make`:

```bash
make help
make setup
make test
make inspect
```

Run a local experiment:

```bash
# Terminal 1
make run-sample

# Terminal 2
make evaluate-local
```

Run the containerized experiment:

```bash
make experiment-compose
```

Generate one report per supported demo surface without executing targets:

```bash
make report-suite
```

Useful override examples:

```bash
make evaluate-local LOCAL_PORT=18080 OUTPUT=./outputs/experiments/local-baseline
make evaluate-compose DURATION=1m SLO_P95_MS=300 OUTPUT=./outputs/experiments/compose-baseline
```

## Quick Start: Local

Create or reuse the project virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run tests:

```bash
make test
```

Generate a k6 script from the sample OpenAPI:

```bash
.venv/bin/python -m perfagent generate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://localhost:8080 \
  --output ./outputs/generated-sample
```

Validate the generated script:

```bash
make inspect
```

## Run The HTTP Demo Experiment

Start the sample HTTP service:

```bash
make run-sample
```

In another terminal, run PerfAgent:

```bash
make evaluate-local
```

Output artifacts are written under:

```text
outputs/sample-payments-api/
├── generated/perf_test.js
├── generated/test_data.json
├── raw/k6_summary.json
├── raw/execution.log
├── processed/contract_analysis.json
├── processed/aligned_timeseries.csv
├── processed/features.json
├── processed/bottleneck_analysis.json
├── processed/metric_contract.yaml
├── reports/report.md
├── reports/report.html
└── state/evaluation_state.json
```

## Containerized Usage

The PerfAgent image bundles Python, the CLI, and native k6:

```bash
make build
```

Run the CLI in a container:

```bash
docker compose run --rm perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://demo-http-payments:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --output ./outputs/sample-payments-api
```

Start the bundled demo applications:

```bash
make demo-up
```

Run PerfAgent against the HTTP demo service through the Compose network:

```bash
make evaluate-compose
```

Build, start demos, run the evaluation, and stop the demos:

```bash
make experiment-compose
```

Generate report artifacts for HTTP, gRPC, WebSocket, and UI without requiring the demo services to be running:

```bash
make report-suite
```

Protocol demo targets:

| Protocol | Compose service | Port | PerfAgent support |
| --- | --- | ---: | --- |
| HTTP/OpenAPI | `demo-http-payments` | `8080` | End-to-end now |
| WebSocket | `demo-websocket-payments` | `8081` | Generated scenario sequence harness and direct execution |
| gRPC | `demo-grpc-payments` | `8082` | Generated proto/stub invocation harness and direct execution |
| UI/Browser | `demo-ui-checkout` | `8083` | Generated browser journey harness with Web Vitals-style metrics |

More details: [docs/demo-applications.md](docs/demo-applications.md).

Demo test plan and testcase inventory: [docs/demo-test-plan.md](docs/demo-test-plan.md).

New extension surfaces:

- `--engine ui` / `--engine browser` generates and executes a Playwright-style browser journey harness.
- `distributed plan` writes a containerized distributed execution plan.
- `distributed coordinate` writes worker commands plus the deterministic merge command for distributed load runs.
- `distributed run` executes the worker commands and merges worker summaries when they are available.
- `distributed merge` combines worker summaries into a merged summary and aligned time-series.
- `profile plan` writes eBPF/system profiler capture plans by default, with runtime-specific profilers available as fallback.
- `profile run` executes available profiler capture/render commands explicitly.
- `evaluate --profile-auto` runs supported profiler capture commands during the load window.
- `capacity search` runs iterative capacity probes and records the first breaking point.
- `observability query-pack` renders and validates provider query packs for Datadog, New Relic, and Elasticsearch.
- `ci comment` renders reusable Markdown for PR comments from `reports/summary.json`.
- `storage dashboard` renders a cross-run trend dashboard from the run store.
- `regression index` and `regression similar` combine deterministic SQL history with optional pgvector retrieval.
- `mcp` exposes stdio MCP-style tools, including `evaluate_service`.
- `--workflow langgraph` runs the evaluation through the optional LangGraph wrapper.

Run the gRPC demo tests:

```bash
make test-grpc
make test-websocket
make test-ui
```

The gRPC demo lives in [examples/demo-apps/grpc-payments-api](examples/demo-apps/grpc-payments-api). It includes `payments.proto`, a Python gRPC server, and container packaging through Docker Compose.

The WebSocket demo lives in [examples/demo-apps/websocket-payments-api](examples/demo-apps/websocket-payments-api). The UI checkout demo lives in [examples/demo-apps/ui-checkout-app](examples/demo-apps/ui-checkout-app).

Generated test artifacts now include:

- k6: `generated/perf_test.js`
- Locust: `generated/locustfile.py`
- JMeter: `generated/jmeter_test_plan.jmx`

Run tool containers after generating/evaluating artifacts:

```bash
make locust-run
make jmeter-run
```

Both targets now import the external tool output back into PerfAgent and regenerate:

- `reports/report.html`
- `reports/report.md`
- `processed/features.json`
- `processed/aligned_timeseries.csv`

The default strategy includes warmup, baseline load, stress, and recovery stages. Capacity output appears in `processed/features.json` and in the report as estimated capacity RPS, first breaking point RPS, headroom, basis, and confidence.

PerfAgent now captures k6 JSONL time-series samples with `--out json=raw/k6_timeseries.jsonl`, buckets them into `processed/aligned_timeseries.csv`, and uses those buckets for capacity and breakpoint detection.

Every evaluation writes both `reports/report.md` and an interactive, self-contained `reports/report.html`. The HTML report embeds the run data locally, so it can be uploaded as a CI artifact and opened without a backend.

The report also includes service-under-test resource metadata when provided: CPU allocation, memory allocation, disk allocation, and image tag.

## CI Pipeline Integration

PerfAgent is intended to be imported as a CI job that produces release-readiness artifacts. Examples are included for common systems:

- [GitHub Actions](examples/ci/github-actions.yml)
- [GitLab CI](examples/ci/gitlab-ci.yml)
- [Jenkins](examples/ci/Jenkinsfile)

CI guide: [docs/ci-integration.md](docs/ci-integration.md).

HTTP service onboarding guide: [docs/onboarding/http-service.md](docs/onboarding/http-service.md).

Capacity and profiling guide: [docs/capacity-and-profiling.md](docs/capacity-and-profiling.md).

Prometheus integration guide: [docs/prometheus-integration.md](docs/prometheus-integration.md).

Dependency analysis guide: [docs/dependency-analysis.md](docs/dependency-analysis.md).

Performance validation questionnaire: [docs/performance-validation-questionnaire.md](docs/performance-validation-questionnaire.md).

Profiling and flame graph backlog: [docs/profiling-flamegraph-backlog.md](docs/profiling-flamegraph-backlog.md).

Production traffic profile guide: [docs/production-traffic-profile.md](docs/production-traffic-profile.md).

Observability integrations guide: [docs/observability-integrations.md](docs/observability-integrations.md).

Continuous performance guide: [docs/continuous-performance.md](docs/continuous-performance.md).

FAQ: [docs/faq.md](docs/faq.md).

Storage architecture: [docs/storage-architecture.md](docs/storage-architecture.md).

MCP extension point: the same workflow can be exposed as MCP tools such as `evaluate_service`, `compare_regression`, `query_runs`, and `generate_report`, allowing IDEs and agent platforms to drive PerfAgent through a standard integration layer.

## CLI Reference

Evaluate a service:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --engine k6 \
  --mode capacity \
  --service-cpu 500m \
  --service-memory 512Mi \
  --service-disk 2Gi \
  --service-image-tag payments-api:v1.2.3 \
  --prometheus-url https://prometheus.example.com \
  --prometheus-service-label payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml \
  --fail-on BLOCK,UNKNOWN \
  --duration 10m \
  --output ./outputs/payments-api
```

Evaluate from a config file:

```bash
.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml
```

Validate Prometheus query coverage:

```bash
.venv/bin/python -m perfagent prometheus validate \
  --prometheus-url https://prometheus.example.com \
  --prometheus-service-label payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml
```

Validate a provider query pack before wiring it into CI:

```bash
.venv/bin/python -m perfagent observability query-pack \
  --provider datadog \
  --service-name payments-api \
  --site datadoghq.com \
  --api-key "$DATADOG_API_KEY" \
  --app-key "$DATADOG_APP_KEY" \
  --output-json ./outputs/datadog-query-pack.json
```

Derive test load from observed production traffic:

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
  --traffic-profile production \
  --output ./outputs/payments-api
```

Enable local AI analysis with Ollama:

```bash
ollama pull llama3.2
ollama serve

.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --llm-provider ollama \
  --llm-model llama3.2 \
  --output ./outputs/payments-api
```

The LLM receives only structured evidence from `features.json`, `bottleneck_analysis.json`, `dependency_analysis.json`, the metric contract, and warnings. It does not calculate metrics or release decisions.

Plan profiler capture and flamegraph rendering commands:

```bash
.venv/bin/python -m perfagent profile plan \
  --runtime go \
  --mode ebpf \
  --pid 12345 \
  --duration-seconds 60 \
  --output-json ./outputs/profile-plan.json
```

Run profiler capture explicitly:

```bash
.venv/bin/python -m perfagent profile run \
  --runtime go \
  --mode ebpf \
  --pid 12345 \
  --duration-seconds 60 \
  --output-json ./outputs/profile-result.json
```

Run profiler capture during an evaluation:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --profile-auto \
  --profile-mode ebpf \
  --profile-pid 12345 \
  --output ./outputs/payments-api
```

Run iterative capacity search:

```bash
.venv/bin/python -m perfagent capacity search \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --min-rps 50 \
  --max-rps 800 \
  --steps 6 \
  --repeats 3 \
  --refinement-steps 3 \
  --output ./outputs/payments-api-capacity
```

Plan distributed worker execution:

```bash
.venv/bin/python -m perfagent distributed coordinate \
  --service-name payments-api \
  --engine k6 \
  --workers 4 \
  --config ./examples/sample-config.yaml \
  --output ./outputs/distributed-coordinate.json
```

Run distributed workers and merge results:

```bash
.venv/bin/python -m perfagent distributed run \
  --service-name payments-api \
  --engine k6 \
  --workers 4 \
  --config ./examples/sample-config.yaml \
  --output ./outputs/distributed-run.json
```

Generate a PR comment body from a completed run:

```bash
.venv/bin/python -m perfagent ci comment \
  --summary ./outputs/payments-api/reports/summary.json \
  --output ./outputs/perfagent-pr-comment.md
```

When `storage.vector_dsn` is configured, or `PERFAGENT_VECTOR_DSN` is set, each evaluation automatically indexes report narratives, summaries, and execution logs into pgvector. Structured metrics, release decisions, capacity, and regression gates remain in SQL/filesystem artifacts.

Save and compare baselines:

```bash
.venv/bin/python -m perfagent baseline save \
  --run-dir ./outputs/payments-api \
  --baseline-dir ./baselines

.venv/bin/python -m perfagent baseline compare \
  --run-dir ./outputs/payments-api \
  --baseline-dir ./baselines
```

Generate artifacts without executing k6:

```bash
.venv/bin/python -m perfagent generate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --output ./outputs/generated/payments-api
```

Summarize an existing run:

```bash
.venv/bin/python -m perfagent analyze \
  --run-dir ./outputs/payments-api
```

## k6 Runtime Strategy

PerfAgent chooses the k6 runtime in this order:

1. Native `k6` on `PATH`
2. Docker fallback using `grafana/k6:latest`
3. Clear skipped execution result if neither runtime is available

Install native k6 on macOS:

```bash
brew install k6
```

Pull the Docker fallback image:

```bash
docker pull grafana/k6:latest
```

## Report Semantics

Release decisions:

- `PASS`: Baseline and stress stay within SLOs
- `WARN`: Baseline is acceptable, but stress breaches SLOs
- `BLOCK`: Expected-load or baseline phase breaches SLOs
- `UNKNOWN`: Missing execution data or insufficient evidence

Bottleneck classification is deterministic first:

- CPU saturation
- CPU limit / throttling
- Memory leak or unbounded cache
- Overloaded service or dependency
- Dependency or unknown
- None detected

## CNCF Demo Recommendation

For a larger ready-made CNCF ecosystem target, use the OpenTelemetry Demo, also known as Astronomy Shop. The official repository describes it as a microservice-based distributed system for demonstrating OpenTelemetry in a near real-world environment, and it supports Docker and Kubernetes deployment paths.

Useful links:

- https://github.com/open-telemetry/opentelemetry-demo
- https://opentelemetry.io/docs/demo/docker-deployment/

## Roadmap

Near-term:

- Split the LangGraph wrapper into finer-grained nodes for each agent stage
- Deepen Prometheus query support and real service/dependency time-series alignment
- Add richer browser and protocol-specific metrics
- Add OpenTelemetry Demo adapter

Later:

- Kubernetes jobs and k6 Operator support
- CI/CD release gates
- Regression comparison between builds
- Dependency-level bottleneck analysis
- Capacity and cost-per-request recommendations
