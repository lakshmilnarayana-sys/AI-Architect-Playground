# Dependency Analysis

PerfAgent supports declared service dependencies so bottleneck analysis can distinguish application saturation from downstream latency, lag, pool exhaustion, or datastore pressure.

Add dependencies to config:

```yaml
dependencies:
  postgres:
    type: postgres
    role: downstream
    criticality: high
    metrics:
      p95_latency_ms: 'pg_query_p95_latency_ms{service="{service}"}'
      connection_pool_utilization_percent: 'pg_connection_pool_utilization_percent{service="{service}"}'
  kafka:
    type: kafka
    role: downstream
    criticality: high
    metrics:
      consumer_lag: 'kafka_consumergroup_lag{service="{service}"}'
```

When `--prometheus-url` is configured, PerfAgent queries dependency metrics, merges them into `processed/aligned_timeseries.csv` as `dep_<dependency>_<metric>` columns, and writes:

```text
raw/dependency_metrics.json
processed/dependency_analysis.json
```

Dependency findings are added to deterministic bottleneck rules and the HTML/Markdown reports.

Optional demo dependencies:

```bash
make dependencies-up
make dependencies-down
```

The dependency profile includes Postgres, Redis, Kafka, Cassandra, and Elasticsearch. These are scaffolding services; useful performance testing still requires realistic schema, data volume, topics, indexes, and client behavior.
