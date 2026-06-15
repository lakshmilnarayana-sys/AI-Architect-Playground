# Observability Integrations

PerfAgent uses observability data for two jobs:

1. derive production traffic profiles
2. collect service/dependency evidence for bottleneck analysis

The executable clients include Prometheus-compatible `/api/v1/query_range`, Datadog `/api/v1/query`, New Relic GraphQL NRQL, and Elasticsearch `_search` traffic-profile and time-series adapters.

You can render and validate provider query packs without running a load test:

```bash
perfagent observability query-pack \
  --provider datadog \
  --service-name payments-api \
  --site datadoghq.com \
  --api-key "$DATADOG_API_KEY" \
  --app-key "$DATADOG_APP_KEY" \
  --output-json ./outputs/datadog-query-pack.json
```

The command reports missing provider configuration and writes the exact rendered query strings or Elasticsearch query templates. Use it as the first CI/onboarding check before relying on production traffic replay or dependency evidence.

Query packs include golden-signal templates for request rate, p95 latency, error rate, CPU, and memory; Kubernetes workload query groups for CPU, memory, restarts, and throttling; dependency metric contracts for Postgres, Redis, Kafka, Cassandra, and Elasticsearch; and provider-specific query templates. The generated JSON includes a `coverage` section and `dependency_contract_validation` so onboarding and CI can see which signal groups are present and which dependency mappings are missing. Treat them as starting packs: real environments still need label, facet, index, and service-name mapping validation.

## Common Mapping

Every non-Prometheus provider now normalizes metric samples into this shape before they are merged into `aligned_timeseries.csv`:

```json
{
  "timestamp": "2026-06-13T10:00:00Z",
  "source": "datadog",
  "service": "payments-api",
  "metric": "p95_latency_ms",
  "value": 420,
  "group": "golden_signal",
  "endpoint": "/v1/payments",
  "dependency": null
}
```

For dependency metrics:

```json
{
  "timestamp": "2026-06-13T10:00:00Z",
  "source": "datadog",
  "service": "payments-api",
  "metric": "dependency_latency_ms",
  "value": 88,
  "group": "dependency",
  "endpoint": null,
  "dependency": "postgres",
}
```

Dependency metric contracts are also emitted by:

```bash
perfagent observability query-pack \
  --provider elasticsearch \
  --service-name payments-api \
  --base-url http://localhost:9200 \
  --index traces-* \
  --output-json ./outputs/elasticsearch-query-pack.json
```

The output includes `dependency_metric_contracts` and `dependency_contract_validation`. For Elasticsearch, pass `dependency_mappings` in config to confirm every dependency has the required index/field mapping.

## Prometheus

```yaml
traffic_profile:
  enabled: true
  source: prometheus
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: route
  request_rate_query: 'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))'
```

```yaml
dependencies:
  postgres:
    type: postgres
    metrics:
      p95_latency_ms: 'pg_query_p95_latency_ms{service="{service}"}'
      connection_pool_utilization_percent: 'pg_connection_pool_utilization_percent{service="{service}"}'
```

## Datadog

Suggested config:

```yaml
observability:
  provider: datadog
  site: datadoghq.com
  api_key_env: DATADOG_API_KEY
  app_key_env: DATADOG_APP_KEY

traffic_profile:
  enabled: true
  source: datadog
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: resource_name
  request_rate_query: 'sum:trace.http.request.hits{service:{service}} by {resource_name}.as_rate()'
  latency_p95_query: 'p95:trace.http.request.duration{service:{service}} by {resource_name}'
  error_rate_query: 'sum:trace.http.request.errors{service:{service}} by {resource_name}.as_rate()'
```

Dependency examples:

```yaml
dependencies:
  postgres:
    type: postgres
    metrics:
      p95_latency_ms: 'p95:postgresql.query.time{service:{service}}'
      connection_pool_utilization_percent: 'avg:postgresql.connections{service:{service}} / avg:postgresql.max_connections{service:{service}} * 100'
  redis:
    type: redis
    metrics:
      p95_latency_ms: 'p95:redis.command.duration{service:{service}}'
      memory_utilization_percent: 'avg:redis.mem.used{service:{service}} / avg:redis.mem.max{service:{service}} * 100'
```

Implemented adapter endpoint:

```text
POST /api/v1/query/timeseries
```

## New Relic

Suggested config:

```yaml
observability:
  provider: newrelic
  account_id_env: NEW_RELIC_ACCOUNT_ID
  api_key_env: NEW_RELIC_API_KEY

traffic_profile:
  enabled: true
  source: newrelic
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: request.uri
  request_rate_query: >
    SELECT rate(count(*), 1 minute)
    FROM Transaction
    WHERE appName = '{service}'
    FACET request.uri
  latency_p95_query: >
    SELECT percentile(duration, 95)
    FROM Transaction
    WHERE appName = '{service}'
    FACET request.uri
  error_rate_query: >
    SELECT percentage(count(*), WHERE error IS true)
    FROM Transaction
    WHERE appName = '{service}'
    FACET request.uri
```

Dependency examples:

```yaml
dependencies:
  kafka:
    type: kafka
    metrics:
      consumer_lag: >
        SELECT max(consumerLag)
        FROM KafkaConsumerSample
        WHERE appName = '{service}'
        FACET topic
  elasticsearch:
    type: elasticsearch
    metrics:
      p95_latency_ms: >
        SELECT percentile(duration, 95)
        FROM DatastoreSample
        WHERE appName = '{service}' AND datastoreType = 'Elasticsearch'
```

Implemented adapter endpoint:

```text
POST https://api.newrelic.com/graphql
```

## ELK / Elasticsearch

Suggested config:

```yaml
observability:
  provider: elasticsearch
  url: https://elasticsearch.example.com
  api_key_env: ELASTICSEARCH_API_KEY
  index: logs-apm-*

traffic_profile:
  enabled: true
  source: elasticsearch
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: url.path
  request_rate_query:
    index: traces-apm-*
    timestamp_field: '@timestamp'
    service_field: service.name
    route_field: url.path
    duration_field: event.duration
    status_field: http.response.status_code
```

Dependency examples:

```yaml
dependencies:
  cassandra:
    type: cassandra
    metrics:
      p95_latency_ms:
        index: metrics-cassandra-*
        metric_field: cassandra.client.request.latency.p95
  elasticsearch:
    type: elasticsearch
    metrics:
      rejected_threads:
        index: metrics-elasticsearch-*
        metric_field: elasticsearch.thread_pool.search.rejected
```

Implemented adapter endpoint:

```text
POST /<index>/_search
```

## Implementation Contract

Provider adapters expose:

```python
collect_traffic_profile(provider_config, service_name, start, end) -> dict
collect_dependency_metrics(provider_config, dependencies, start, end) -> dict
```

Current provider adapter module:

```python
from perfagent.collectors.observability_adapters import (
    collect_observability_timeseries,
    collect_observability_traffic_profile,
    validate_provider_query_pack,
)
```

Then PerfAgent can keep the same deterministic analysis path:

```text
provider query
  -> normalized traffic profile
  -> derived strategy
  -> normalized provider metric rows
  -> generated load test
  -> aligned time-series
  -> features
  -> bottleneck rules
  -> optional AI explanation
```
