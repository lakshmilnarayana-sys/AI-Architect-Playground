# Capacity, Breakpoints, And Profiling

PerfAgent answers three related questions:

1. What load did the service sustain?
2. Where did the service breach its SLO?
3. What profiling evidence should engineers inspect next?

## Capacity Fields

`processed/features.json` includes:

- `stable_rps`: k6 observed request rate across the run.
- `peak_rps`: highest observed RPS in aligned time-series rows.
- `estimated_capacity_rps`: highest observed RPS before the first SLO breach, or peak RPS if no breach occurred.
- `breaking_point_rps`: RPS at the first latency or error-rate SLO breach.
- `capacity_basis`: explanation of how capacity was estimated.
- `capacity_confidence`: `low`, `medium`, or later `high` as richer time-series arrives.
- `headroom_rps`: difference between estimated capacity and first breaking point when available.
- `capacity_limit_phase`: phase where capacity was first limited.
- `capacity_limit_reason`: why capacity was limited, such as `latency_slo_breach`, `error_slo_breach`, `latency_and_error_slo_breach`, `slo_not_breached_within_tested_range`, or `insufficient_timeseries_rows`.
- `capacity_safe_phase`: phase for the highest observed RPS before the first SLO breach.
- `capacity_stress_phase`: phase for the first SLO breach.

This is intentionally evidence-based. PerfAgent does not claim capacity beyond the tested range.

## Time-Series Source

PerfAgent runs k6 with both:

```text
--summary-export raw/k6_summary.json
--out json=raw/k6_timeseries.jsonl
```

The JSONL file is parsed into 10-second buckets in `processed/aligned_timeseries.csv`. Each row contains:

- timestamp
- test phase
- RPS
- p95 latency
- p99 latency
- error rate percent
- virtual users

The feature extractor sorts timestamped rows before breakpoint and capacity detection so the first breach is chronological even if ingestion produced rows out of order. If the JSONL file is missing or aligned rows are unavailable, PerfAgent falls back to summary-level evidence, sets `capacity_confidence` to `low`, uses `capacity_basis` of `insufficient aligned time-series rows for capacity estimate`, and sets `capacity_limit_reason` to `insufficient_timeseries_rows`.

The same aligned rows are embedded into `reports/report.html` for an interactive chart, phase filter, and sortable time-series table.

## Breakpoint Semantics

A breakpoint is the first point where either:

- p95 latency exceeds `--slo-p95-ms`, or
- error rate exceeds `--slo-error-rate`.

For a useful capacity run, use staged load that includes baseline and stress phases. If the service never breaches an SLO, the report says the tested peak was sustained, not that the service has infinite capacity.

When a breach is detected, `capacity_safe_phase` names the highest-RPS pre-breach phase and `capacity_stress_phase` names the breaching phase. If no breach occurs, `capacity_safe_phase` names the highest tested phase and `capacity_stress_phase` remains empty.

## Profiling Artifacts

Attach profiling output to a run:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --profile ./profiles/cpu.pprof \
  --profile ./profiles/heap.pprof \
  --output ./outputs/payments-api
```

Supported artifact types are intentionally broad:

- Go `pprof`
- Java JFR
- Python `py-spy`
- Node.js Clinic
- collapsed stacks
- Speedscope JSON

PerfAgent stores these under:

```text
raw/profiles/
raw/profiling_artifacts.json
```

The report links the attached artifacts but does not infer root cause from profiles yet. That keeps the current MVP rule intact: code calculates evidence, and higher-level analysis explains only evidence that exists.

## CI Gates

Use `--fail-on` to make CI fail when selected decisions occur:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --fail-on BLOCK,UNKNOWN \
  --output ./outputs/payments-api
```
