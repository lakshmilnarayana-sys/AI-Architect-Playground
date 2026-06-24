# Runbook: Downstream Failures (dependency_timeout)

**Alert:** StreamFlixDownstreamFailures · **Severity:** SEV3

## Symptom
Downstream call error ratio above 10% for 10m; upstream service degraded due to failing dependency.

## Confirm
- PromQL: `sum by (service)(rate(downstream_requests_total{code=~"5..|error"}[5m])) / sum by (service)(rate(downstream_requests_total[5m]))`
- `kubectl --context kind-streamflix -n streamflix-prod logs <pod>` (check downstream error messages)

## Likely cause
Downstream service is unhealthy, network partition, or a dependency fault (`make fault SVC=<downstream-svc> MODE=dependency_timeout`).

## Mitigation
1. Identify the failing downstream service from the `service` label in the alert.
2. Clear the fault on the downstream service: `make fault SVC=<downstream-svc> MODE=clear`.
3. Verify downstream error ratio returns below 10% after the downstream recovers.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
