# Production Traffic Profile Ingestion

PerfAgent can query production observability data, derive per-endpoint traffic mix and load stages, generate matching load tests, and measure whether a microservice can sustain production-like and peak traffic.

Enable it with:

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

Or configure it:

```yaml
traffic_profile:
  enabled: true
  source: prometheus
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: route
  request_rate_query: 'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))'
```

PerfAgent writes:

```text
processed/traffic_profile.json
processed/test_strategy.yaml
generated/perf_test.js
reports/report.html
```

The derived strategy includes:

- endpoint mix weights
- production-like RPS
- observed peak RPS
- peak traffic phase using `peak_multiplier`
- recovery phase

The generated k6 script uses weighted endpoint selection so the test request mix resembles observed production traffic.

Limits:

- Payload distributions are still synthetic unless seed data is supplied.
- Endpoint matching depends on Prometheus route/path labels matching OpenAPI paths.
- Non-HTTP traffic profile derivation is not yet first-class.
