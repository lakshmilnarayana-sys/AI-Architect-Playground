# Observability And Dependencies

## Golden Signals

Capture the four golden signals:

- Latency: p95, p99, max p95, max p99, service p95/p99 where available.
- Traffic: RPS, request count, virtual users, endpoint mix, production-like and peak traffic.
- Errors: client failures, failed checks, 4xx/5xx, dependency errors, timeout rates.
- Saturation: CPU, memory, CPU throttling, pod restarts, queue depth, connection pool utilization, GC/heap, disk, network.

If saturation metrics are missing, do not classify CPU/memory/dependency bottlenecks with high confidence.

## Provider Strategy

Prefer configurable queries because label names vary by platform.

Supported PerfAgent provider concepts:

- Prometheus-compatible query API
- Datadog query API
- New Relic GraphQL/NRQL
- Elasticsearch `_search`

Normalize provider data into:

```json
{
  "source": "prometheus|datadog|newrelic|elasticsearch",
  "production_like_rps": 100,
  "peak_rps": 150,
  "endpoint_mix": [
    {"path": "/v1/payments", "observed_rps": 80, "weight": 0.8}
  ]
}
```

## Prometheus

Use direct query endpoints when available:

```yaml
prometheus:
  enabled: true
  url: https://prometheus.example.com
  service_label: payments-api
  query_config: ./examples/prometheus-queries.yaml
```

Traffic profile:

```yaml
traffic_profile:
  enabled: true
  source: prometheus
  endpoint_label: route
  request_rate_query: 'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))'
```

Validation:

```bash
.venv/bin/python -m perfagent prometheus validate \
  --prometheus-url https://prometheus.example.com \
  --prometheus-service-label payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml
```

## Datadog

Config pattern:

```yaml
observability:
  provider: datadog
  datadog:
    site: datadoghq.com
    api_key_env: DATADOG_API_KEY
    app_key_env: DATADOG_APP_KEY

traffic_profile:
  enabled: true
  source: datadog
  endpoint_label: resource_name
  request_rate_query: 'sum:trace.http.request.hits{service:{service}} by {resource_name}.as_rate()'
```

Check these before trusting results:

- service tag matches deployed service
- resource name maps to OpenAPI path or route
- units are seconds vs milliseconds
- request hits are rate-normalized
- errors and latency use same scope as traffic

## New Relic

Config pattern:

```yaml
observability:
  provider: newrelic
  newrelic:
    account_id_env: NEW_RELIC_ACCOUNT_ID
    api_key_env: NEW_RELIC_API_KEY

traffic_profile:
  enabled: true
  source: newrelic
  endpoint_label: request.uri
  nrql: >
    SELECT rate(count(*), 1 second) AS rps
    FROM Transaction
    WHERE appName = '{service}'
    FACET request.uri
```

Check:

- account ID is correct
- application name matches service
- facets use route template, not high-cardinality raw URL, when possible
- NRQL time window matches lookback intent

## Elasticsearch / ELK

Config pattern:

```yaml
observability:
  provider: elasticsearch
  elasticsearch:
    url: https://elasticsearch.example.com
    api_key_env: ELASTICSEARCH_API_KEY
    index: traces-apm-*

traffic_profile:
  enabled: true
  source: elasticsearch
  endpoint_field: url.path
  service_field: service.name
```

Check:

- index pattern contains trace or access-log documents
- timestamp field is consistent
- URL field is route-like or normalized
- counts are converted to rates using the lookback window

## Dependencies

Declare dependencies explicitly:

```yaml
dependencies:
  postgres:
    type: postgres
    role: downstream
    criticality: high
    metrics:
      p95_latency_ms: 'pg_query_p95_latency_ms{service="{service}"}'
      connection_pool_utilization_percent: 'pg_connection_pool_utilization_percent{service="{service}"}'
  redis:
    type: redis
    role: downstream
    metrics:
      p95_latency_ms: 'redis_command_p95_latency_ms{service="{service}"}'
      memory_utilization_percent: 'redis_memory_utilization_percent{service="{service}"}'
  kafka:
    type: kafka
    role: downstream
    metrics:
      consumer_lag: 'kafka_consumergroup_lag{service="{service}"}'
```

Dependency evidence should be merged into aligned time-series as `dep_<name>_<metric>`.

## Dependency Bottleneck Rules

Postgres/database:
- high query p95 plus service p95 breach suggests database latency.
- high connection pool utilization suggests pool saturation.
- high lock wait or slow query count strengthens database bottleneck confidence.

Redis/cache:
- high command latency suggests cache/network pressure.
- high memory utilization plus eviction/rejected command metrics suggests cache saturation.

Kafka/queue:
- increasing consumer lag during load plus slow recovery suggests consumer capacity issue.
- producer errors or broker throttling suggest broker or quota pressure.

Cassandra:
- high read/write latency, tombstones, pending compactions, or coordinator timeouts point to datastore pressure.

Elasticsearch:
- rejected search/write threads, high query latency, merge pressure, or JVM heap pressure indicate search cluster bottleneck.

Unknown dependency:
- user-facing p95 rises, CPU/memory are not saturated, and errors increase after latency rises.
- report missing metrics required to confirm the dependency.

## Service Resources

Include in report when known:

- CPU allocation/request/limit
- memory allocation/request/limit
- disk allocation
- image tag
- replica count
- runtime

These values do not prove saturation by themselves. They contextualize CPU/request, memory/request, throttling, and scaling recommendations.
