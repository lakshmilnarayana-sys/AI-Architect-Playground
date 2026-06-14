# Reporting, AI, And Governance

## Report Requirements

Every report should include:

1. Executive Summary
2. Service Under Test
3. Test Inputs
4. Test Strategy
5. API Coverage
6. SLOs
7. Results
8. Time-Series Findings
9. Capacity And Breakpoint
10. Bottleneck Analysis
11. Dependency Analysis
12. Profiling Evidence
13. Recommendations
14. Release Decision
15. Missing Metrics
16. Appendix

Interactive HTML should include:

- light/dark mode toggle
- clear x-axis and y-axis labels
- hover tooltips
- p95/p99/RPS/error overlays
- breakpoint marker
- phase bands
- evidence table
- dependency findings
- service resources and image tag
- downloadable JSON/CSV artifact references

## Chart Rules

Always label:

- x-axis: time or phase progression
- y-axis left: latency in ms or error rate percent
- y-axis right: RPS or virtual users

Do not put unrelated metrics on one unlabeled axis.

Good chart overlays:

- p95 latency vs RPS
- p99 latency vs RPS
- error rate vs RPS
- CPU/memory vs RPS
- dependency p95/lag/utilization vs service p95

Add markers for:

- first SLO breach
- estimated capacity
- breaking point
- baseline/stress/recovery phase boundaries

## AI Role

AI receives only structured evidence:

- service metadata
- SLO
- strategy
- features
- bottleneck classification
- dependency findings
- metric contract
- warnings/missing metrics

AI outputs:

- plain-language summary
- bottleneck explanation
- confidence
- evidence list
- recommendations
- missing metrics

AI must not:

- invent metrics
- invent traces
- invent downstream root causes
- calculate p95/p99/RPS
- set release decision
- override deterministic classifier

## Ollama Pattern

Local AI config:

```yaml
llm:
  enabled: true
  provider: ollama
  model: llama3.2
  base_url: http://localhost:11434
```

Command:

```bash
ollama pull llama3.2
ollama serve

.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --llm-provider ollama \
  --llm-model llama3.2
```

If Ollama is unavailable, report deterministic results and mark AI narrative as disabled or failed.

## Bottleneck Evidence Rules

CPU saturation:
- p95 rises
- CPU > 85%
- error rate may rise
- memory not primary driver

CPU throttling:
- p95 rises
- throttling > 5%
- CPU limit/request context available

Memory pressure:
- memory grows continuously
- memory does not recover after load drops
- GC/heap metrics strengthen confidence

Dependency or unknown:
- p95 rises
- CPU/memory not saturated
- dependency p95/lag/pool metrics rise, or dependency metrics are missing

Overload:
- error rate > SLO
- p95 rises
- capacity phase or stress phase breach

## Profiling

Accept profiling artifacts as attachments:

- Go pprof
- Java JFR
- Python py-spy
- Node clinic.js
- flamegraphs
- heap dumps
- GC logs

Treat profiles as supporting evidence. Do not infer production root cause from a profile without correlating it to the load test window.

## MCP Extension

PerfAgent can be exposed as an MCP server with tools:

- `evaluate_service`
- `generate_test`
- `compare_regression`
- `query_runs`
- `validate_prometheus`
- `collect_traffic_profile`
- `generate_report`

MCP should call the same deterministic workflow as the CLI. Do not create a separate analysis path.

## Review Checklist

Before finalizing performance work:

- Were test inputs and SLOs explicit?
- Were artifacts generated?
- Did the engine execute or was the run intentionally skipped?
- Were results imported for external tools?
- Was time-series alignment produced?
- Were features deterministic?
- Was bottleneck classification evidence-backed?
- Was dependency analysis included where configured?
- Was service resource metadata included where provided?
- Was baseline/regression comparison done when requested?
- Were missing metrics called out?
- Did the final report avoid invented numbers?
