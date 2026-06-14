# PerfAgent Project Map

## Key Commands

Help:

```bash
.venv/bin/python -m perfagent --help
```

Evaluate:

```bash
.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml
```

Generate only:

```bash
.venv/bin/python -m perfagent generate \
  --service-name payments-api \
  --openapi ./examples/sample-openapi.yaml \
  --target-url http://localhost:8080 \
  --output ./outputs/generated
```

Analyze existing run:

```bash
.venv/bin/python -m perfagent analyze \
  --run-dir ./outputs/sample-payments-api
```

Import external results:

```bash
.venv/bin/python -m perfagent import-results \
  --run-dir ./outputs/sample-payments-api \
  --tool locust \
  --result ./outputs/sample-payments-api/raw/locust_stats.csv \
  --service-name sample-payments-api \
  --runtime python \
  --target-url http://localhost:8080 \
  --slo-p95-ms 500 \
  --slo-error-rate 1
```

Validate Prometheus:

```bash
.venv/bin/python -m perfagent prometheus validate \
  --prometheus-url http://localhost:9090 \
  --prometheus-service-label sample-payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml
```

Regression compare:

```bash
.venv/bin/python -m perfagent regression compare \
  --run-dir ./outputs/sample-payments-api \
  --db-path ./outputs/perfagent.db \
  --fail-on-regression
```

## Make Targets

Common targets:

```bash
make setup
make test
make compose-config
make demo-up
make demo-down
make evaluate-local
make locust-run
make jmeter-run
make dependencies-up
make dependencies-down
```

## Code Areas

CLI:
- `perfagent/cli.py`

Workflow:
- `perfagent/workflow.py`

Config:
- `perfagent/config.py`

OpenAPI:
- `perfagent/parsers/openapi_parser.py`

Generators:
- `perfagent/generators/k6_generator.py`
- `perfagent/generators/locust_generator.py`
- `perfagent/generators/jmeter_generator.py`
- `perfagent/generators/grpc_generator.py`
- `perfagent/generators/websocket_generator.py`
- `perfagent/generators/report_renderer.py`

Collectors:
- `perfagent/collectors/k6_collector.py`
- `perfagent/collectors/external_results.py`
- `perfagent/collectors/protocol_collectors.py`
- `perfagent/collectors/prometheus_collector.py`
- `perfagent/collectors/traffic_profile.py`
- `perfagent/collectors/observability_adapters.py`
- `perfagent/collectors/profiling_collector.py`

Analyzers:
- `perfagent/analyzers/alignment.py`
- `perfagent/analyzers/features.py`
- `perfagent/analyzers/bottlenecks.py`
- `perfagent/analyzers/dependencies.py`
- `perfagent/analyzers/slo.py`

Storage:
- `perfagent/storage/run_store.py`
- `perfagent/storage/postgres_store.py`

LLM:
- `perfagent/llm/client.py`
- `perfagent/llm/prompts.py`
- `perfagent/llm/schemas.py`

Tests:
- `tests/test_*`

## Artifact Layout

Each run should create:

```text
input/openapi.yaml
generated/perf_test.js
generated/locustfile.py
generated/jmeter_test_plan.jmx
generated/grpc_load.py
generated/websocket_load.py
generated/test_data.json
raw/k6_summary.json
raw/k6_timeseries.jsonl
raw/prometheus_metrics.json
raw/dependency_metrics.json
raw/execution_result.json
processed/contract_analysis.json
processed/test_strategy.yaml
processed/metric_contract.yaml
processed/aligned_timeseries.csv
processed/features.json
processed/bottleneck_analysis.json
processed/dependency_analysis.json
processed/traffic_profile.json
processed/ai_analysis.json
reports/report.md
reports/report.html
reports/summary.json
state/evaluation_state.json
```

## Implementation Conventions

- Keep deterministic calculations out of LLM code.
- Keep provider-specific API calls in collectors.
- Keep report rendering in templates and renderer.
- Keep CLI options mapped through config resolution.
- Add tests for every new command, parser, generator, collector, analyzer, and storage behavior.
- Prefer fixture-sized tests over live network dependencies.
- Run `make test`, `make compose-config`, and a relevant smoke command before pushing.
