# StreamFlix Platform Phase 2 — Alerting + Runbooks (Design)

**Date:** 2026-06-24
**Status:** Approved (design) — proceeding to plan
**Author:** Lakshmi Narayana Vommi (with Claude)
**Builds on:** Phase 1 (`2026-06-24-streamflix-platform-design.md`) — live kind cluster `streamflix`, 35 services in `streamflix-prod`, kube-prometheus-stack (Prometheus + Alertmanager + Grafana) + Loki + Tempo in `observability`.

## 1. Goal

Make StreamFlix faults produce **real alerts**: PrometheusRules that fire on actual
cluster metrics when a fault is injected, routed through the already-running
Alertmanager to a local webhook **alert-sink**, with **runbooks** linked from each
alert. Alert metadata (severity, failure_mode, team) aligns with the incident agent's
ground truth so Phase 3 can wire the agent to live alerts.

## 2. Existing assets aligned to

- `src/incident/alerting.py` — `ALERT_THRESHOLDS` ground truth (metric + threshold per
  failure mode) and severities. Our rule thresholds/severities match these.
- `src/incident/kubernetes.py` — the 8 failure-mode keys; our `failure_mode` alert label
  uses these exact keys.
- `graph/` ownership edges — `team` alert label/annotation derives from `OWNS_SERVICE`.
- `data/runbooks.yaml`, `src/incident/mitigate.py` — existing runbook/mitigation content
  our markdown runbooks align with.
- Phase 1 metrics: Go service exposes `http_requests_total{service,code}`,
  `http_request_duration_seconds_bucket{service,code,le}`,
  `downstream_requests_total{service,target,code}`. kube-state-metrics + cAdvisor provide
  pod/container metrics.

## 3. Decisions (confirmed)

| Decision | Choice |
|---|---|
| Alert scope | Real-injectable K8s modes + app-level SLO alerts (aligned to `alerting.py`). Extended modes with no real metric (kafka/redis/db/cert) are out of scope. |
| Phase 2 delivery | Local in-cluster **webhook alert-sink** (Phase 3 swaps it for the Slack mock). |
| Alert-sink language | Tiny **Go** service (consistent with `streamflix-service`). |
| Rules authored, not generated | PromQL expressions are the real artifact; only labels/severity align to `alerting.py`/graph. |

## 4. Architecture

```
fault injected → real metric crosses threshold → PrometheusRule fires
  → Prometheus → Alertmanager (route/group/inhibit) → alert-sink webhook (GET /alerts to view)
```

All on real metrics. No simulated alerts.

## 5. Components

### 5.1 PrometheusRules — `platform/alerting/rules/streamflix-alerts.yaml`

One `PrometheusRule` CR (group `streamflix.rules`) in `observability`, labelled
`release: kps` so the operator adopts it. Each rule has labels
`severity` (SEV1/SEV2/SEV3), `failure_mode` (matching `kubernetes.py` keys where
applicable), plus `service` (app-metric alerts) or `pod` (k8s-metric alerts; service is
derivable from the `<service>-service-<hash>` pod name). Annotations: `summary`,
`description`, `runbook_url` (by failure-mode convention).

App-level SLO alerts (carry `service` directly):
- **StreamFlixHighErrorRate** — `sum by (service)(rate(http_requests_total{code=~"5.."}[5m])) / sum by (service)(rate(http_requests_total[5m])) > 0.05`, `for: 5m`, SEV2.
- **StreamFlixHighLatencyP95** — `histogram_quantile(0.95, sum by (service,le)(rate(http_request_duration_seconds_bucket[5m]))) > 0.5`, `for: 10m`, SEV3. (Baseline ~0.02s; the Phase 1 cpu_throttle test hit ~0.48s.)
- **StreamFlixDownstreamFailures** — `sum by (service)(rate(downstream_requests_total{code=~"5..|error"}[5m])) / sum by (service)(rate(downstream_requests_total[5m])) > 0.1`, `for: 10m`, SEV3, `failure_mode: dependency_timeout`.

Kubernetes failure-mode alerts (namespace `streamflix-prod`):
- **StreamFlixCPUThrottling** — `sum by (pod)(rate(container_cpu_cfs_throttled_periods_total[5m])) / sum by (pod)(rate(container_cpu_cfs_periods_total[5m])) > 0.25`, `for: 10m`, SEV3, `failure_mode: cpu_throttle`.
- **StreamFlixOOMKilled** — `max by (pod,container)(kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}) == 1`, `for: 1m`, SEV2, `failure_mode: oom_kill`.
- **StreamFlixPodCrashLooping** — `increase(kube_pod_container_status_restarts_total[10m]) >= 3`, `for: 2m`, SEV2, `failure_mode: pod_restart`.
- **StreamFlixImagePullBackOff** — `max by (pod)(kube_pod_container_status_waiting_reason{reason=~"ImagePullBackOff|ErrImagePull"}) == 1`, `for: 5m`, SEV3, `failure_mode: image_pull_backoff`.
- **StreamFlixMemoryNearLimit** — `sum by (pod)(container_memory_working_set_bytes{container!=""}) / sum by (pod)(kube_pod_container_resource_limits{resource="memory"}) > 0.9`, `for: 15m`, SEV3, `failure_mode: memory_leak` (best-effort).

`hpa_maxed` / `node_pressure` remain best-effort/out (no HPA deployed; documented).

### 5.2 Alertmanager configuration

Route all `streamflix.rules` alerts: group by `[alertname, service, pod]`,
`group_wait 10s`, `repeat_interval 1h`; **inhibition** — a firing SEV1/SEV2 for a
service suppresses SEV3 for the same service. Single receiver = the alert-sink webhook
(`http://alert-sink.observability.svc:8080/webhook`). Delivered via the kps Alertmanager
(an `AlertmanagerConfig` CR selected by the Alertmanager, or kps values — the plan picks
the approach the live chart accepts).

### 5.3 Alert-sink — `platform/alerting/alert-sink/` (Go)

Minimal HTTP service, image `localhost:5001/streamflix-alert-sink:dev`, deployed in
`observability` (Deployment + Service `alert-sink:8080`):
- `POST /webhook` — accepts Alertmanager webhook JSON, stores the last 100 alerts
  in-memory, logs a one-line summary per alert.
- `GET /alerts` — returns received alerts as JSON (newest first) for inspection.
- `GET /healthz`.
Stateless, no persistence (restart clears history — fine for a demo).

### 5.4 Runbooks — `platform/runbooks/<failure_mode>.md`

One markdown runbook per alert (`cpu_throttle`, `oom_kill`, `pod_restart`,
`image_pull_backoff`, `memory_leak`, `high_error_rate`, `high_latency`,
`downstream_failures`). Each: **Symptom**, **Confirm** (the PromQL + `kubectl` to verify),
**Likely cause**, **Mitigation** (aligned to `mitigate.py` templates + `data/runbooks.yaml`),
**Owning team** (from graph), **Escalation** (from `escalation_policies.yaml`). The alert
`runbook_url` annotation references the runbook by failure-mode convention.

## 6. Repo layout & UX

```
platform/alerting/
  rules/streamflix-alerts.yaml      # PrometheusRule CR
  alertmanager/                     # AlertmanagerConfig CR (or values patch) + receiver
  alert-sink/                       # Go service + Dockerfile
platform/runbooks/<failure_mode>.md
```
Makefile: `make alerts` (build+load sink image, deploy sink, apply rules + AM config) and
`make alerts-verify`.

## 7. Acceptance criteria (the "it's real" test)

1. `kubectl get prometheusrule streamflix-alerts -n observability` present; rules visible
   in Prometheus `/rules`.
2. alert-sink pod Running; `GET /alerts` returns `[]` initially.
3. `make fault SVC=playback MODE=cpu_throttle VALUE=2 TTL=300` → within the rule window,
   **StreamFlixCPUThrottling** (and/or StreamFlixHighLatencyP95) shows `firing` in
   Alertmanager, and **alert-sink `/alerts` contains it** with `failure_mode=cpu_throttle`
   and a `runbook_url`.
4. Drive `oom_kill` on billing → **StreamFlixOOMKilled** fires and is delivered to the
   sink. Clear → alert resolves.
5. Each fired alert's `runbook_url` resolves to an existing `platform/runbooks/*.md`.

## 8. Non-goals (Phase 2)

No Slack/Jira (Phase 3), no on-call paging/escalation execution (Phase 3), no Backstage
(Phase 4). Rules authored, not generated. `hpa_maxed`/`node_pressure` best-effort.

## 9. Risks & mitigations

- **kps Alertmanager not selecting our config** → plan verifies `alertmanagerConfigSelector`
  / uses the approach the live chart accepts; `make alerts-verify` checks the receiver is
  active in Alertmanager `/api/v2/status`.
- **k8s-metric alerts lack a `service` label** → carry `pod` (service derivable from pod
  name); documented for the Phase 3 agent mapping.
- **Alert timing in a demo** → thresholds/`for` windows kept short enough to fire within a
  couple minutes under injected fault + loadgen traffic.
