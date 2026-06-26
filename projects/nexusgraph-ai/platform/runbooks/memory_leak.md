# Runbook: Memory Near Limit (memory_leak)

**Alert:** StreamFlixMemoryNearLimit · **Severity:** SEV3

## Symptom
Working set memory above 90% of pod memory limit for 15m; OOMKill risk imminent.

## Confirm
- PromQL: `sum by (pod)(container_memory_working_set_bytes{namespace="streamflix-prod", container!=""}) / sum by (pod)(kube_pod_container_resource_limits{namespace="streamflix-prod", resource="memory"}) > 0.9`
- `kubectl --context kind-streamflix -n streamflix-prod top pod <pod>` (check memory usage)

## Likely cause
Memory leak in application, memory limit set too low, or a memory fault (`make fault SVC=<svc> MODE=memory_leak`).

## Mitigation
1. Clear the fault if injected: `make fault SVC=<svc> MODE=clear`.
2. Restart the pod to reclaim leaked memory: `kubectl --context kind-streamflix -n streamflix-prod rollout restart deployment/<svc>`.
3. Raise the memory limit or fix the leak in the application code.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
