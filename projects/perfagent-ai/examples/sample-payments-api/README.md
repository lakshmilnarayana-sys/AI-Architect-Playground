# HTTP Sample Payments API

Small stdlib Python service for local PerfAgent evaluation.

Environment knobs:

- `DEMO_BASE_LATENCY_MS`: base synthetic latency, default `20`
- `DEMO_JITTER_MS`: random latency jitter, default `15`
- `DEMO_ERROR_RATE`: probability of returning HTTP 503 from `POST /v1/payments`, default `0`

Run directly:

```bash
python examples/sample-payments-api/app.py
```

Run with Compose:

```bash
docker compose --profile demo up --build demo-http-payments
```
