# Demo Applications Test Plan

This plan defines the tests PerfAgent should cover for the bundled demo applications. It is written for local development, CI smoke runs, and future release validation.

## Scope

Demo applications:

| ID | Demo | Protocol | Compose service | Port | Contract/source |
| --- | --- | --- | --- | ---: | --- |
| APP-HTTP | Sample Payments API | HTTP/OpenAPI | `demo-http-payments` | `8080` | `examples/sample-payments-api/openapi.yaml` |
| APP-GRPC | gRPC Payments API | gRPC | `demo-grpc-payments` | `8082` | `examples/demo-apps/grpc-payments-api/protos/payments.proto` |
| APP-WS | WebSocket Payments API | WebSocket | `demo-websocket-payments` | `8081` | message examples in app/tests |
| APP-UI | UI Checkout App | Browser UI + HTTP API | `demo-ui-checkout` | `8083` | `/openapi.json` and page workflow |

Framework capabilities under test:

- contract parsing
- synthetic test data generation
- k6, Locust, JMeter, gRPC, and WebSocket test generation
- k6/gRPC/WebSocket direct execution
- Locust/JMeter result import
- Prometheus-compatible metric collection
- dependency metric configuration
- time-series alignment
- feature extraction
- capacity and breakpoint detection
- bottleneck and dependency classification
- baseline/regression comparison
- interactive HTML report generation
- CI artifact and PR comment examples

## Entry Criteria

- `make setup` completed.
- Docker is running.
- `make compose-config` succeeds.
- Demo services build successfully.
- Local ports `8080`, `8081`, `8082`, and `8083` are available or tests run inside Compose network.

## Exit Criteria

- Required automated tests pass.
- Each demo has at least one successful functional test.
- HTTP demo has full end-to-end PerfAgent report generation.
- gRPC and WebSocket demos execute through their protocol engines and generate reports.
- Locust and JMeter runs regenerate PerfAgent reports after import.
- Capacity mode writes capacity and breakpoint fields.
- Regression compare command can detect a synthetic regression.
- HTML report is self-contained and interactive.
- Known gaps are listed explicitly.

## Test Levels

| Level | Purpose | Command examples |
| --- | --- | --- |
| Unit | Validate parsers, generators, analyzers, collectors, stores | `make test` |
| Contract | Validate OpenAPI/proto/schema extraction | `pytest tests/test_openapi_parser.py tests/test_grpc_payments_api.py` |
| Functional | Validate demo app behavior | `make test-grpc`, `make test-websocket`, `make test-ui` |
| Smoke performance | Short execution with report generation | `perfagent evaluate --duration 10s` |
| Capacity | Step-load mode with capacity and breakpoint fields | `perfagent evaluate --mode capacity` |
| External tool import | Locust/JMeter execution plus report import | `make locust-run`, `make jmeter-run` |
| CI regression | Compare current run against stored baseline/history | `perfagent regression compare` |

## Environment Matrix

| ENV ID | Environment | Purpose | Required? |
| --- | --- | --- | --- |
| ENV-LOCAL | Host Python + local demo target | Fast local development | Yes |
| ENV-COMPOSE | PerfAgent container + Compose demo services | Containerized framework validation | Yes |
| ENV-CI | GitHub Actions or equivalent | PR/nightly regression | Yes |
| ENV-OBS | Existing Prometheus-compatible endpoint | Golden signals and dependency metrics | Optional |
| ENV-VENDOR | Datadog/New Relic/Elasticsearch sandbox | Provider adapter validation | Optional |

## Test Data

Use deterministic non-PII data:

```json
{
  "customerId": "cust_test_1001",
  "amount": 49.99,
  "currency": "GBP",
  "paymentMethod": "card"
}
```

Negative cases:

- missing `customerId`
- missing `amount`
- missing `currency`
- invalid or malformed JSON for WebSocket
- unreachable target URL
- missing metrics/provider credentials

## Functional Test Cases

| TC ID | Area | Scenario | Steps | Expected result | Automation |
| --- | --- | --- | --- | --- | --- |
| TC-FUNC-001 | HTTP | Health endpoint responds | Start `demo-http-payments`; call `/health` | `200 OK` | Add/maintain HTTP smoke test |
| TC-FUNC-002 | HTTP | Create payment accepts valid payload | POST `/v1/payments` with required fields and `x-request-id` | Expected success status and payment ID | `tests/test_sample_payments_api.py` |
| TC-FUNC-003 | HTTP | Create payment rejects missing fields | POST missing required body fields | `400`, missing field list | `tests/test_sample_payments_api.py` |
| TC-FUNC-004 | HTTP | OpenAPI contract exposes required fields | Parse sample OpenAPI | endpoints, body schema, headers, path/query params extracted | `tests/test_openapi_parser.py` |
| TC-FUNC-005 | HTTP | Metrics endpoint exposes demo counters | Call `/metrics` after requests | request/error/latency metrics present | Recommended |
| TC-FUNC-006 | gRPC | Proto defines payment RPC | Compile/read `payments.proto` | `payments.Payments/CreatePayment` exists | `tests/test_grpc_payments_api.py` |
| TC-FUNC-007 | gRPC | CreatePayment accepts valid request | Invoke service implementation with valid message | authorized response with `pay_grpc_` ID | `tests/test_grpc_payments_api.py` |
| TC-FUNC-008 | gRPC | CreatePayment rejects missing fields | Invoke with missing required fields | rejected status | `tests/test_grpc_payments_api.py` |
| TC-FUNC-009 | WebSocket | Valid payment message round trip | Send valid JSON message | authorized response with latency fields | `tests/test_websocket_payments_api.py` |
| TC-FUNC-010 | WebSocket | Missing fields rejected | Send message missing required fields | rejected response with missing field reason | `tests/test_websocket_payments_api.py` |
| TC-FUNC-011 | WebSocket | Malformed JSON rejected gracefully | Send invalid JSON frame | error response, no server crash | Recommended |
| TC-FUNC-012 | UI | Checkout page renders controls | Load page HTML | form fields and action controls exist | `tests/test_ui_checkout_app.py` |
| TC-FUNC-013 | UI | Checkout API accepts valid payload | POST `/api/checkout` | checkout ID and `channel=ui` | `tests/test_ui_checkout_app.py` |
| TC-FUNC-014 | UI | Checkout API rejects missing fields | POST missing required fields | `400`, missing fields | `tests/test_ui_checkout_app.py` |
| TC-FUNC-015 | UI | UI OpenAPI describes checkout endpoint | Load `/openapi.json` or app schema | required fields match page/API | `tests/test_ui_checkout_app.py` |

## PerfAgent Generation Test Cases

| TC ID | Scenario | Steps | Expected artifacts | Automation |
| --- | --- | --- | --- | --- |
| TC-GEN-001 | Generate HTTP k6 test from OpenAPI | Run `perfagent generate` for sample OpenAPI | `perf_test.js`, `test_data.json`, `contract_analysis.json` | `tests/test_cli_workspace.py`, `tests/test_k6_generator.py` |
| TC-GEN-002 | Generate Locust file | Run generate/evaluate skip-run | `generated/locustfile.py` | `tests/test_locust_generator.py` |
| TC-GEN-003 | Generate JMeter plan | Run generate/evaluate skip-run | `generated/jmeter_test_plan.jmx` | `tests/test_jmeter_generator.py` |
| TC-GEN-004 | Generate gRPC harness | Run generate/evaluate skip-run | `generated/grpc_load.py` emits JSON and uses gRPC readiness | `tests/test_protocol_generators.py` |
| TC-GEN-005 | Generate WebSocket harness | Run generate/evaluate skip-run | `generated/websocket_load.py` emits JSON and handles connection failures | `tests/test_protocol_generators.py` |
| TC-GEN-006 | Generate deterministic synthetic data | Parse schema and generate payloads | required fields populated, no PII | `tests/test_synthetic_data.py` |

## Performance Execution Test Cases

| TC ID | Engine | Scenario | Command | Expected result |
| --- | --- | --- | --- | --- |
| TC-PERF-001 | k6 | HTTP smoke run | `perfagent evaluate --engine k6 --duration 10s` | `raw/k6_summary.json`, `processed/features.json`, `reports/report.html` |
| TC-PERF-002 | k6 | HTTP capacity run | `perfagent evaluate --engine k6 --mode capacity --duration 10s` | capacity fields and breakpoint basis in `features.json` |
| TC-PERF-003 | k6 | Unreachable HTTP target | Evaluate against unused port | graceful failure/UNKNOWN or WARN with execution evidence; report generated |
| TC-PERF-004 | Locust | External Locust execution | `make locust-run` | Locust CSV imported; PerfAgent HTML/MD report regenerated |
| TC-PERF-005 | JMeter | External JMeter execution | `make jmeter-run` | JTL imported; PerfAgent HTML/MD report regenerated |
| TC-PERF-006 | gRPC | gRPC protocol execution | `perfagent evaluate --engine grpc --target-url http://localhost:8082` | protocol summary normalized; report generated |
| TC-PERF-007 | gRPC | gRPC unreachable target | evaluate against unused port | failed requests captured without runaway output; report generated |
| TC-PERF-008 | WebSocket | WebSocket protocol execution | `perfagent evaluate --engine websocket --target-url http://localhost:8081` | message/client summary normalized; report generated |
| TC-PERF-009 | WebSocket | WebSocket unreachable target | evaluate against unused port | connection failure captured as failed request; report generated |
| TC-PERF-010 | UI | UI checkout API performance via HTTP engine | evaluate using UI OpenAPI target | report generated for `/api/checkout` |
| TC-PERF-011 | UI | Browser journey performance | `perfagent evaluate --engine ui` | generated Playwright-style journey executes or reports missing Playwright evidence | Implemented MVP |

## Observability And Dependency Test Cases

| TC ID | Area | Scenario | Steps | Expected result | Automation |
| --- | --- | --- | --- | --- | --- |
| TC-OBS-001 | Prometheus | Validate custom queries | Run `perfagent prometheus validate` with mocked/real endpoint | available/missing metrics reported | `tests/test_prometheus_collector.py` |
| TC-OBS-002 | Prometheus | Collect service metrics | Evaluate with `--prometheus-url` and query config | `raw/prometheus_metrics.json`; aligned CSV includes service/infra columns | Existing collector tests |
| TC-OBS-003 | Traffic profile | Derive endpoint mix from Prometheus | Enable `--traffic-profile production` | `processed/traffic_profile.json`; weighted strategy/script | `tests/test_traffic_profile.py` |
| TC-OBS-004 | Datadog | Normalize traffic profile | Mock Datadog response | endpoint mix and peak RPS calculated | `tests/test_observability_adapters.py` |
| TC-OBS-005 | New Relic | Normalize traffic profile | Mock NRQL GraphQL response | endpoint mix and RPS calculated | `tests/test_observability_adapters.py` |
| TC-OBS-006 | Elasticsearch | Normalize traffic profile | Mock aggregation response | endpoint counts converted to RPS | `tests/test_observability_adapters.py` |
| TC-OBS-007 | Dependencies | Merge dependency metrics | Configure Postgres/Redis/Kafka metrics | `raw/dependency_metrics.json`, `processed/dependency_analysis.json`, report section | `tests/test_dependency_analysis.py` |
| TC-OBS-008 | Missing metrics | Required metric absent | Mock missing query result | warning/missing evidence and non-hallucinated report | Recommended |

## Analysis And Reporting Test Cases

| TC ID | Area | Scenario | Expected result | Automation |
| --- | --- | --- | --- | --- |
| TC-AN-001 | Alignment | k6 JSONL bucketed into 10-second rows | phase, RPS, p95/p99, errors, VUs extracted | `tests/test_alignment.py` |
| TC-AN-002 | Features | SLO breach detected | first breach timestamp/phase and decision fields set | `tests/test_feature_extraction.py` |
| TC-AN-003 | Capacity | Capacity and breakpoint computed | estimated capacity, breaking point, confidence, basis | `tests/test_feature_extraction.py` |
| TC-AN-004 | Bottleneck | CPU/memory/error rules classify findings | bottleneck, confidence, evidence list | `tests/test_bottleneck_rules.py` |
| TC-AN-005 | Dependencies | Dependency bottleneck evidence appears | dependency findings in markdown and HTML | `tests/test_dependency_analysis.py` |
| TC-AN-006 | Report | Markdown and HTML generated | report sections exist; self-contained HTML | `tests/test_report_renderer.py` |
| TC-AN-007 | Interactive chart | Axes, theme toggle, phase controls exist | chart labels and dark/light mode controls visible | Existing renderer tests plus recommended browser check |
| TC-AN-008 | AI disabled | LLM disabled path is safe | deterministic report generated with AI disabled note | `tests/test_ollama_llm.py` |
| TC-AN-009 | Ollama | Ollama explanation uses structured evidence | `processed/ai_analysis.json` and report AI section | `tests/test_ollama_llm.py` |

## Storage, Baseline, And CI Test Cases

| TC ID | Area | Scenario | Steps | Expected result | Automation |
| --- | --- | --- | --- | --- | --- |
| TC-CI-001 | SQLite store | Record and list run | Evaluate or call store | run persisted and listed | `tests/test_run_storage.py` |
| TC-CI-002 | Retention | Delete expired runs | Apply retention | old runs removed | `tests/test_run_storage.py` |
| TC-CI-003 | Baseline file | Save and compare baseline | `baseline save`, `baseline compare` | p95/RPS/error deltas printed | `tests/test_config_engine_baseline.py` |
| TC-CI-004 | Regression DB | Detect regression vs latest baseline | `regression compare --fail-on-regression` | exit code `2`, findings JSON | `tests/test_regression_cli.py` |
| TC-CI-005 | Postgres store | Record/list through optional backend | fake or real Postgres connection | SQL schema/upsert/list behavior works | `tests/test_postgres_store.py` |
| TC-CI-006 | GitHub Actions | PR workflow uploads and comments report | inspect example workflow | report artifact and PR comment steps present | Recommended static test |
| TC-CI-007 | Complexity trigger | PR changes mapped to smoke/targeted/full | classify changed file list | expected recommended profile | `tests/test_pr_complexity.py` |

## Security And Safety Test Cases

| TC ID | Scenario | Expected result |
| --- | --- | --- |
| TC-SAFE-001 | No real PII in generated data | deterministic synthetic IDs and safe values only |
| TC-SAFE-002 | No secrets in generated scripts/reports | auth placeholders only; env vars referenced by name |
| TC-SAFE-003 | Destructive endpoints avoided or flagged | DELETE/unsafe operations require explicit handling |
| TC-SAFE-004 | Provider credentials absent | adapters fail gracefully or skip with warning |
| TC-SAFE-005 | Raw logs truncated when huge | execution logs do not become unbounded |

## Recommended Command Sequence

Local verification:

```bash
make test
make compose-config
make demo-up
```

HTTP end-to-end:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --engine k6 \
  --output ./outputs/sample-payments-api
```

Capacity:

```bash
.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --mode capacity \
  --duration 10s \
  --output ./outputs/sample-payments-api-capacity
```

gRPC:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name grpc-payments-api \
  --openapi ./examples/sample-openapi.yaml \
  --target-url http://localhost:8082 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --engine grpc \
  --output ./outputs/grpc-payments-api
```

WebSocket:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name websocket-payments-api \
  --openapi ./examples/sample-openapi.yaml \
  --target-url http://localhost:8081 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --engine websocket \
  --output ./outputs/websocket-payments-api
```

External tools:

```bash
make locust-run
make jmeter-run
```

Regression:

```bash
.venv/bin/python -m perfagent regression compare \
  --run-dir ./outputs/sample-payments-api \
  --db-path ./outputs/perfagent.db \
  --fail-on-regression
```

Cleanup:

```bash
make demo-down
```

## Known Gaps To Track

- Browser UI load testing supports configured journeys, browser metrics, LCP, optional error screenshots, trace files, and video artifact paths; richer journey recording remains future work.
- gRPC harness can invoke configured protobuf stubs/RPC methods and optionally compile protos at runtime with inferred module/stub/request names.
- WebSocket harness supports configured message scenarios and deterministic JSON Schema-style message generation.
- Dependency containers are scaffolding; realistic dependency tests require schemas, data volumes, topics, indexes, and client behavior.
- Vendor observability adapters normalize traffic profiles and provider time-series rows; full provider-specific dependency metric contracts still need hardening.
- Capacity confidence is lower without service, infra, and dependency time-series.
