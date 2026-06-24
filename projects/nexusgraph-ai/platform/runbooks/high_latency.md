# Runbook: High Latency (high_latency)

**Alert:** StreamFlixHighLatencyP95 · **Severity:** SEV3

## Symptom
p95 request latency above 500ms for 10m; user-facing slowness.

## Confirm
- PromQL: `histogram_quantile(0.95, sum by (service, le)(rate(http_request_duration_seconds_bucket[5m])))`
- `kubectl --context kind-streamflix -n streamflix-prod top pod` (check CPU/memory pressure)

## Likely cause
CPU throttling, downstream latency, resource contention, or a latency fault (`make fault SVC=<svc> MODE=high_latency`).

## Mitigation
1. Clear cpu_throttle or latency fault if injected: `make fault SVC=<svc> MODE=clear`.
2. Check throttling alerts and downstream health dashboards.
3. Verify p95 latency returns below 500ms after mitigation.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
