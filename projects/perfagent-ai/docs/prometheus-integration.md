# Prometheus Integration

PerfAgent can query an existing Prometheus-compatible HTTP API directly. You do not need to run a local observability stack.

Use:

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
  --output ./outputs/payments-api
```

Use custom PromQL when your metric names or labels differ:

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

PerfAgent calls:

```text
GET /api/v1/query_range
```

and stores raw query results in:

```text
raw/prometheus_metrics.json
```

Prometheus values are merged into:

```text
processed/aligned_timeseries.csv
```

## Default Query Targets

The MVP queries common Kubernetes/service metrics:

- `cpu_percent`
- `memory_mb`
- `cpu_throttling_percent`
- `pod_restarts`
- `service_request_rate`
- `service_error_rate_percent`

The default queries are intentionally conventional and may need adjustment for each platform’s metric names and labels. The current service selector uses the provided service label against common `pod` and `service` labels.

## Custom Query Config

Create a YAML or JSON file with a top-level `queries` mapping:

```yaml
queries:
  cpu_percent: 'sum(rate(container_cpu_usage_seconds_total{namespace="payments", pod=~".*{service}.*"}[1m])) * 100'
  memory_mb: 'sum(container_memory_working_set_bytes{namespace="payments", pod=~".*{service}.*"}) / 1024 / 1024'
  cpu_throttling_percent: 'sum(rate(container_cpu_cfs_throttled_periods_total{pod=~".*{service}.*"}[1m])) / sum(rate(container_cpu_cfs_periods_total{pod=~".*{service}.*"}[1m])) * 100'
  pod_restarts: 'sum(kube_pod_container_status_restarts_total{pod=~".*{service}.*"})'
  service_request_rate: 'sum(rate(http_server_requests_seconds_count{service="{service}"}[1m]))'
  service_error_rate_percent: 'sum(rate(http_server_requests_seconds_count{service="{service}", status=~"5.."}[1m])) / sum(rate(http_server_requests_seconds_count{service="{service}"}[1m])) * 100'
```

`{service}` is replaced with the value from `--prometheus-service-label`. Use this to map PerfAgent’s normalized metric names to platform-specific labels such as `app`, `job`, `service_name`, `namespace`, or `pod`.

Supported normalized query names today:

- `cpu_percent`
- `memory_mb`
- `cpu_throttling_percent`
- `pod_restarts`
- `service_request_rate`
- `service_error_rate_percent`

## Requirements

The endpoint must be reachable from where PerfAgent runs and support Prometheus-compatible `query_range` responses.

If a query fails, PerfAgent records a warning and continues with the available k6 evidence.
