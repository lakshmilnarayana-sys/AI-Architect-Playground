# Runbook: OOMKilled (oom_kill)

**Alert:** StreamFlixOOMKilled · **Severity:** SEV2

## Symptom
Container terminated with reason OOMKilled; pod restarting.

## Confirm
- PromQL: `max by (pod, container)(kube_pod_container_status_last_terminated_reason{namespace="streamflix-prod", reason="OOMKilled"}) == 1`
- `kubectl --context kind-streamflix -n streamflix-prod describe pod <pod>` (check Last State and OOMKilled reason)

## Likely cause
Memory limit too low for workload, memory leak in application, or a memory fault (`make fault SVC=<svc> MODE=oom_kill`).

## Mitigation
1. Clear the fault if injected: `make fault SVC=<svc> MODE=clear`.
2. Raise memory limit or fix the memory leak in the application.
3. Confirm no new OOMKilled terminations: re-check PromQL returns no results.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
