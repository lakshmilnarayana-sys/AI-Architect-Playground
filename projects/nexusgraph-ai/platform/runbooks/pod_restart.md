# Runbook: Crash Loop (pod_restart)

**Alert:** StreamFlixPodCrashLooping · **Severity:** SEV2

## Symptom
Pod restarted >= 3 times in 10m; container is crash-looping.

## Confirm
- PromQL: `increase(kube_pod_container_status_restarts_total{namespace="streamflix-prod"}[10m]) >= 3`
- `kubectl --context kind-streamflix -n streamflix-prod get pods` (check RESTARTS column)

## Likely cause
Application crash, unhandled exception, misconfiguration, or a crash fault (`make fault SVC=<svc> MODE=pod_restart`).

## Mitigation
1. Clear the fault if injected: `make fault SVC=<svc> MODE=clear`.
2. Inspect previous container logs: `kubectl --context kind-streamflix -n streamflix-prod logs --previous <pod>`.
3. Fix the crash cause and redeploy; confirm restarts settle to 0.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
