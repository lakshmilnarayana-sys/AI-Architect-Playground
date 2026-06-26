# Runbook: Downstream Failures (dependency_timeout)

**Alert:** StreamFlixDownstreamFailures · **Severity:** SEV3

## Symptom
Downstream call error ratio above 10% for 10m; upstream service degraded due to failing dependency.

## Confirm
- PromQL: `sum by (service)(rate(downstream_requests_total{code=~"5..|error"}[5m])) / sum by (service)(rate(downstream_requests_total[5m]))`
- `kubectl --context kind-streamflix -n streamflix-prod logs <pod>` (check downstream error messages)

## Likely cause
Downstream service is unhealthy, network partition, or an injected error-rate fault on the downstream service (`make fault SVC=<downstream-svc> MODE=error_rate`).

## Mitigation
1. Identify the failing downstream service from the `service` and `target` labels in the alert.
2. To reproduce or confirm: inject `MODE=error_rate` on the FAILING DOWNSTREAM service — the one the alerting service calls: `make fault SVC=<downstream-svc> MODE=error_rate`.
3. Clear the fault on the downstream service once confirmed or remediated: `make fault SVC=<downstream-svc> MODE=clear`.
4. Verify downstream error ratio returns below 10% after the downstream recovers.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
