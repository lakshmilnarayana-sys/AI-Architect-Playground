# Runbook: High Error Rate (high_error_rate)

**Alert:** StreamFlixHighErrorRate · **Severity:** SEV2

## Symptom
5xx HTTP error ratio above 5% for 5m; users experiencing request failures.

## Confirm
- PromQL: `sum by (service)(rate(http_requests_total{code=~"5.."}[5m])) / sum by (service)(rate(http_requests_total[5m]))`
- `kubectl --context kind-streamflix -n streamflix-prod logs <pod>` (check for error traces)

## Likely cause
Failing downstream dependency, application bug, resource exhaustion, or an error-rate fault (`make fault SVC=<svc> MODE=error_rate`).

## Mitigation
1. Identify the failing dependency: check downstream health and error logs.
2. If an error-rate fault was injected, clear it: `make fault SVC=<svc> MODE=clear`.
3. To reproduce or confirm: `make fault SVC=<svc> MODE=error_rate` (forces 5xx on every request).
4. Verify 5xx ratio returns below 5% after mitigation.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
