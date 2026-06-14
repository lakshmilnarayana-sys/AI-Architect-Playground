---
name: performance-engineer
description: End-to-end performance engineering for microservices and PerfAgent AI. Use when Codex needs to design, implement, run, analyze, or review performance tests; generate k6, Locust, JMeter, gRPC, WebSocket, or UI load tests; configure Prometheus, Datadog, New Relic, Elasticsearch, dependency metrics, capacity/breakpoint detection, baselines, regression gates, CI/CD continuous performance, profiling evidence, or engineering-grade performance reports.
---

# Performance Engineer

## Operating Rule

Code calculates the evidence. AI explains the evidence.

Never let an LLM invent metrics, capacity, breakpoints, SLO status, dependency behavior, or release decisions. Generate deterministic artifacts first, then use AI only for narrative, recommendations, and missing-metric explanation.

## Workflow

1. Clarify service scope: protocol, API contract, runtime, target URL, expected load, SLOs, dependencies, environment, and observability source.
2. Generate or inspect the test strategy: warmup, baseline, stress/capacity, recovery, traffic mix, thresholds, and test duration.
3. Generate load assets from contract or examples: payloads, headers, auth placeholders, path/query values, and protocol-specific clients.
4. Execute the smallest valid run first. Confirm reports and raw artifacts exist before scaling up.
5. Align load, service, infrastructure, and dependency metrics into comparable time buckets.
6. Extract features deterministically: RPS, p95/p99, errors, saturation, capacity, breakpoint, recovery, dependency findings.
7. Classify likely bottlenecks with rules before AI narrative.
8. Produce an evidence-backed report with pass/warn/block/unknown and prioritized fixes.
9. Persist the run and compare against baseline/history in CI.

## Reference Routing

Read only the reference file needed for the task:

- Test design, workloads, SLOs, payload quality, and acceptance criteria: `references/test-design.md`.
- Protocol/tool implementation for HTTP, gRPC, WebSocket, UI, k6, Locust, and JMeter: `references/protocols-and-tools.md`.
- Prometheus, Datadog, New Relic, Elasticsearch, service resources, and dependencies such as DB/Kafka/Redis/Cassandra/Elasticsearch: `references/observability-and-dependencies.md`.
- Capacity detection, breakpoint search, baselines, PR regression, run storage, retention, and CI/CD: `references/capacity-regression-ci.md`.
- Report structure, interactive HTML, AI/Ollama role, MCP extension, and review checklist: `references/reporting-ai-governance.md`.
- PerfAgent codebase map, command examples, artifact paths, and implementation conventions: `references/perfagent-project-map.md`.

## PerfAgent Defaults

Prefer the CLI-first flow:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./examples/sample-openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --engine k6 \
  --mode standard \
  --output ./outputs/payments-api
```

Use `--mode capacity` when the user asks for capacity, breakpoint, headroom, or "where does it break".

Use `--traffic-profile production` only when observability data has route/path/facet labels that map to the API contract.

## Review Heuristics

- A performance conclusion without raw artifacts is incomplete.
- A capacity number without a load-stage basis and SLO breach rule is weak.
- A bottleneck claim without aligned load plus service/infra/dependency evidence is speculative.
- A regression gate without stored history or a named baseline is not enforceable.
- A report without missing metrics encourages false confidence.
- A synthetic payload that violates business rules invalidates endpoint results.

## Completion Criteria

For implementation work, verify at minimum:

```bash
make test
make compose-config
.venv/bin/python -m perfagent --help
```

For runtime changes, also run a small `evaluate` smoke command for the touched engine and confirm `reports/report.html`, `reports/summary.json`, `processed/features.json`, and `processed/aligned_timeseries.csv` exist.
