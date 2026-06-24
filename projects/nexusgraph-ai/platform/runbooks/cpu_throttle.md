# Runbook: CPU Throttling (cpu_throttle)

**Alert:** StreamFlixCPUThrottling · **Severity:** SEV3

## Symptom
Container CPU throttled ratio above 25% for 10m; elevated request latency.

## Confirm
- PromQL: `sum by (pod)(rate(container_cpu_cfs_throttled_periods_total{namespace="streamflix-prod"}[5m])) / sum by (pod)(rate(container_cpu_cfs_periods_total{namespace="streamflix-prod"}[5m]))`
- `kubectl --context kind-streamflix -n streamflix-prod describe pod <pod>` (check CPU limits)

## Likely cause
CPU limit too low for current load, or a CPU-bound fault (`make fault SVC=<svc> MODE=cpu_throttle`).

## Mitigation
1. Clear the fault if injected: `make fault SVC=<svc> MODE=clear`.
2. Raise the container CPU limit or scale replicas.
3. Verify throttle ratio returns below 25%.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
