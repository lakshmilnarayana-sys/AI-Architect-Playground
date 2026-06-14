# Protocols And Tools

## Engine Selection

Use this default mapping:

- HTTP API: k6 first, Locust/JMeter for compatibility or team preference.
- gRPC: generated Python gRPC harness first; later add ghz or k6 gRPC when proto/stubs are available.
- WebSocket: generated Python `websockets` harness for message round-trip and connection behavior.
- UI/browser: Playwright for browser journey performance; k6 browser can be added later for load-oriented UI journeys.
- Mixed microservice demo: OpenTelemetry Demo/Astronomy Shop for CNCF-style realistic topology.

## k6

Use k6 for contract-driven HTTP tests:

- Generate one JS test per service.
- Use OpenAPI paths/methods/payloads.
- Add thresholds for p95 and failed request rate.
- Emit summary JSON and JSONL time-series.
- Keep output artifacts deterministic.

Required outputs:

```text
generated/perf_test.js
raw/k6_summary.json
raw/k6_timeseries.jsonl
raw/execution.log
processed/aligned_timeseries.csv
processed/features.json
reports/report.html
```

Container execution should use the bundled Docker image or compose profile when local k6 is missing.

## Locust

Use Locust when teams need Python user behavior or complex workflows:

- Generate `locustfile.py`.
- Run headless in CI.
- Export CSV and optional native HTML.
- Import results into PerfAgent so the same report path is generated.

Expected import command:

```bash
.venv/bin/python -m perfagent import-results \
  --tool locust \
  --result ./outputs/sample-payments-api/raw/locust_stats.csv \
  --run-dir ./outputs/sample-payments-api \
  --service-name sample-payments-api \
  --runtime python \
  --target-url http://localhost:8080 \
  --slo-p95-ms 500 \
  --slo-error-rate 1
```

Prefer history CSV for time-series buckets when available.

## JMeter

Use JMeter when the organization already has JVM/JMeter infrastructure:

- Generate `jmeter_test_plan.jmx`.
- Run non-GUI mode in CI.
- Export `.jtl`.
- Import `.jtl` into PerfAgent.

Expected import command:

```bash
.venv/bin/python -m perfagent import-results \
  --tool jmeter \
  --result ./outputs/sample-payments-api/raw/jmeter_results.jtl \
  --run-dir ./outputs/sample-payments-api \
  --service-name sample-payments-api \
  --runtime python \
  --target-url http://localhost:8080 \
  --slo-p95-ms 500 \
  --slo-error-rate 1
```

## gRPC

Use gRPC tests when the service exposes unary or streaming RPCs:

- Prefer `.proto` and generated client stubs.
- If stubs are missing, generated harness should at least validate channel readiness and report failures.
- Treat missing RPC method implementation as incomplete coverage, not proof of service failure.
- Capture status codes, deadlines, retries, message sizes, and latency.

Useful gRPC metrics:

- request count
- OK/error status count
- deadline exceeded count
- unavailable count
- p95/p99 latency
- stream open duration
- messages per second
- client-side retry count

Generated PerfAgent gRPC harness emits JSON so it can be normalized into k6-like summary metrics.

## WebSocket

Use WebSocket tests for persistent connections and message round trips:

- Validate connection establishment.
- Send representative messages, not only ping/pong.
- Track connection errors separately from message errors.
- Capture session duration, messages/sec, round-trip latency, reconnects, and close codes.

Generated PerfAgent WebSocket harness emits JSON rows per worker and records connection failure as failed requests instead of crashing.

## UI Performance

Use UI tests for user journey timing, not raw service capacity:

- browser launch and page load timing
- first meaningful view for the journey
- API wait time from the browser perspective
- DOM interaction latency
- checkout/search/login workflow duration
- errors and console failures

Do not use browser UI tests as the primary way to find backend capacity. Use them to verify end-user impact at selected load levels.

## Tool Result Normalization

Normalize all engines into a common shape:

```json
{
  "metrics": {
    "http_reqs": {"count": 1000, "rate": 200},
    "http_req_duration": {"p(95)": 420, "p(99)": 800},
    "http_req_failed": {"rate": 0.01},
    "checks": {"passes": 990, "fails": 10},
    "iterations": {"count": 1000}
  }
}
```

Then derive:

- RPS
- p95/p99 latency
- error rate
- request count
- SLO breach phase
- capacity and breakpoint
- report decision
