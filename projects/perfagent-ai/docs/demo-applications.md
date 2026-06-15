# Demo Applications

PerfAgent ships local demo targets by protocol:

| Protocol | Compose service | Port | Current framework support |
| --- | --- | ---: | --- |
| HTTP/OpenAPI | `demo-http-payments` | `8080` | Supported now |
| WebSocket | `demo-websocket-payments` | `8081` | Generated harness, schema-derived messages, and direct execution supported |
| gRPC | `demo-grpc-payments` | `8082` | Generated harness, optional proto compilation, and direct execution supported |
| UI/Browser | `demo-ui-checkout` | `8083` | Configured Playwright-style journey harness, browser metrics, traces, video, and screenshots supported |

The gRPC demo lives in `examples/demo-apps/grpc-payments-api`. It exposes `payments.Payments/CreatePayment` on port `8082` and is covered by tests that compile the protobuf contract and validate the service implementation.

Full coverage plan: [Demo Applications Test Plan](demo-test-plan.md).

```bash
make test-grpc
```

The WebSocket demo is covered by message-level tests:

```bash
make test-websocket
```

The UI checkout demo exposes a browser page plus `/api/checkout`, `/openapi.json`, and `/metrics`:

```bash
make test-ui
```

Start all demo services:

```bash
docker compose --profile demo up --build
```

Tool containers are available for generated plans:

```bash
make locust-run
make jmeter-run
```

These commands prepare the PerfAgent workspace, run the tool container, import the tool result file, and regenerate the standard PerfAgent Markdown/HTML report under `outputs/<service>/reports/`.

Run PerfAgent against the HTTP demo from the host:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 1m \
  --output ./outputs/sample-payments-api
```

Run PerfAgent against the HTTP demo from Compose:

```bash
docker compose run --rm perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://demo-http-payments:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 1m \
  --output ./outputs/sample-payments-api
```

## CNCF-Ready Demo Candidate

Use the OpenTelemetry Demo, also known as Astronomy Shop, when you want a larger CNCF ecosystem target. It is a microservice-based distributed system intended to show OpenTelemetry in a near real-world environment, with Docker and Kubernetes deployment docs.
