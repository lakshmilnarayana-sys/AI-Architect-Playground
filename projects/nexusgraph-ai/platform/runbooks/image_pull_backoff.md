# Runbook: ImagePullBackOff (image_pull_backoff)

**Alert:** StreamFlixImagePullBackOff · **Severity:** SEV3

## Symptom
Pod cannot pull its image for 5m; container stuck in waiting state with reason ImagePullBackOff or ErrImagePull.

## Confirm
- PromQL: `max by (pod)(kube_pod_container_status_waiting_reason{namespace="streamflix-prod", reason=~"ImagePullBackOff|ErrImagePull"}) == 1`
- `kubectl --context kind-streamflix -n streamflix-prod describe pod <pod>` (check Events for pull errors)

## Likely cause
Invalid image tag, image removed from registry, registry credentials expired, or a bad deployment that references a non-existent image.

## Mitigation
1. Fix image tag or registry credentials in the deployment spec.
2. Run `make deploy` (or `kubectl --context kind-streamflix set image deployment/<svc> <svc>=<correct-image>`) to restore a valid image.
3. Verify pod transitions to Running and waiting reason clears.

## Owning team
Derived from graph `OWNS_SERVICE` for the affected service (e.g. Platform Engineering for playback/manifest/cdn-routing).

## Escalation
Per `data/escalation_policies.yaml` for the service/severity.
