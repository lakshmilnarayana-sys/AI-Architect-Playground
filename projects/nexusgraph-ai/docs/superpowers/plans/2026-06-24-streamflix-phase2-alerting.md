# StreamFlix Platform Phase 2 — Alerting + Runbooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make injected StreamFlix faults produce real Prometheus alerts that route through Alertmanager to a local webhook alert-sink, each linked to a runbook.

**Architecture:** Author PrometheusRules (real PromQL on live cluster metrics) labelled `release: kps` so the existing kube-prometheus-stack operator adopts them; configure the already-running Alertmanager (via kps helm values — global config, to avoid the namespaced `AlertmanagerConfig` matcher pitfall) to route all StreamFlix alerts to a tiny in-cluster Go alert-sink; write one markdown runbook per alert, referenced by each alert's `runbook_url`.

**Tech Stack:** Go 1.22 (alert-sink, built in-container), Prometheus Operator CRDs (PrometheusRule), kube-prometheus-stack (Helm), Alertmanager, kind, kubectl, helm.

## Global Constraints

- Cluster is `kind` named `streamflix`, context `kind-streamflix`. Every `kubectl`/`helm` command passes `--context kind-streamflix` / `--kube-context kind-streamflix`. NEVER target the `*-prod` EKS contexts.
- Apps in namespace `streamflix-prod`; alerting objects (PrometheusRule, alert-sink, Alertmanager) in `observability`.
- All new code under `platform/`. Local registry `localhost:5001`; alert-sink image `localhost:5001/streamflix-alert-sink:dev`.
- Alert labels use `failure_mode` keys matching `src/incident/kubernetes.py` exactly: `oom_kill`, `pod_restart`, `cpu_throttle`, `image_pull_backoff`, `memory_leak` (also `dependency_timeout` for the downstream alert). Severities `SEV1`/`SEV2`/`SEV3` align with `src/incident/alerting.py`.
- PrometheusRule CR must carry label `release: kps` (the operator's ruleSelector matches it; Phase 1 set `ruleSelectorNilUsesHelmValues: false`).
- Commit author name `lakshminarayana-sys`, signed, no Claude trailer: `git -c user.name=lakshminarayana-sys commit -m "..."`. Only commit each task's own files; never `git add -A` (the repo has unrelated untracked files).
- Repo root is `/Users/lnv/Documents/maven`; project dir `/Users/lnv/Documents/maven/projects/nexusgraph-ai`. Run `make`/`docker` from `platform/` (i.e. `projects/nexusgraph-ai/platform`).
- Verified-present metrics (do not invent others): `http_requests_total{service,code}`, `http_request_duration_seconds_bucket{service,code,le}`, `downstream_requests_total{service,target,code}`, `container_cpu_cfs_throttled_periods_total`, `container_cpu_cfs_periods_total`, `kube_pod_container_status_last_terminated_reason{reason}`, `kube_pod_container_status_waiting_reason{reason}` (0 series at rest — only during a pull failure), `kube_pod_container_status_restarts_total`, `container_memory_working_set_bytes`, `kube_pod_container_resource_limits{resource="memory"}`.

---

### Task 1: Alert-sink Go service

**Files:**
- Create: `platform/alerting/alert-sink/go.mod`
- Create: `platform/alerting/alert-sink/store.go`
- Create: `platform/alerting/alert-sink/store_test.go`
- Create: `platform/alerting/alert-sink/main.go`
- Create: `platform/alerting/alert-sink/Dockerfile`

**Interfaces:**
- Produces: image `localhost:5001/streamflix-alert-sink:dev` exposing `POST /webhook` (Alertmanager webhook JSON in), `GET /alerts` (stored alerts as JSON, newest first), `GET /healthz`. Listens on `:8080`.
- `store.go` exports `type AlertStore` with `NewAlertStore(capacity int) *AlertStore`, `Add(a ReceivedAlert)`, `List() []ReceivedAlert` (newest first), and `type ReceivedAlert struct { Status string; Labels map[string]string; Annotations map[string]string; ReceivedAt time.Time }`.

- [ ] **Step 1: Write `go.mod`**

```
module streamflix-alert-sink

go 1.22
```

- [ ] **Step 2: Write the failing test `store_test.go`**

```go
package main

import "testing"

func TestAlertStoreNewestFirst(t *testing.T) {
	s := NewAlertStore(10)
	s.Add(ReceivedAlert{Status: "firing", Labels: map[string]string{"alertname": "A"}})
	s.Add(ReceivedAlert{Status: "firing", Labels: map[string]string{"alertname": "B"}})
	got := s.List()
	if len(got) != 2 {
		t.Fatalf("want 2, got %d", len(got))
	}
	if got[0].Labels["alertname"] != "B" {
		t.Fatalf("want newest-first (B), got %s", got[0].Labels["alertname"])
	}
}

func TestAlertStoreCapacityEvictsOldest(t *testing.T) {
	s := NewAlertStore(2)
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "A"}})
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "B"}})
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "C"}})
	got := s.List()
	if len(got) != 2 {
		t.Fatalf("want capacity 2, got %d", len(got))
	}
	if got[0].Labels["alertname"] != "C" || got[1].Labels["alertname"] != "B" {
		t.Fatalf("want [C,B], got [%s,%s]", got[0].Labels["alertname"], got[1].Labels["alertname"])
	}
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd platform/alerting/alert-sink && go test ./... 2>&1 | head`
Expected: FAIL — `undefined: NewAlertStore`.

- [ ] **Step 4: Write `store.go`**

```go
package main

import (
	"sync"
	"time"
)

type ReceivedAlert struct {
	Status      string            `json:"status"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`
	ReceivedAt  time.Time         `json:"receivedAt"`
}

type AlertStore struct {
	mu       sync.Mutex
	capacity int
	items    []ReceivedAlert // oldest..newest
}

func NewAlertStore(capacity int) *AlertStore {
	return &AlertStore{capacity: capacity}
}

func (s *AlertStore) Add(a ReceivedAlert) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if a.ReceivedAt.IsZero() {
		a.ReceivedAt = time.Now().UTC()
	}
	s.items = append(s.items, a)
	if len(s.items) > s.capacity {
		s.items = s.items[len(s.items)-s.capacity:]
	}
}

func (s *AlertStore) List() []ReceivedAlert {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]ReceivedAlert, len(s.items))
	for i, a := range s.items { // reverse → newest first
		out[len(s.items)-1-i] = a
	}
	return out
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd platform/alerting/alert-sink && go test ./...`
Expected: PASS (`ok  streamflix-alert-sink`).

- [ ] **Step 6: Write `main.go`** (webhook receiver + viewer)

```go
package main

import (
	"encoding/json"
	"log"
	"net/http"
)

var store = NewAlertStore(100)

// Alertmanager webhook payload (subset).
type amPayload struct {
	Status string `json:"status"`
	Alerts []struct {
		Status      string            `json:"status"`
		Labels      map[string]string `json:"labels"`
		Annotations map[string]string `json:"annotations"`
	} `json:"alerts"`
}

func handleWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var p amPayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	for _, a := range p.Alerts {
		store.Add(ReceivedAlert{Status: a.Status, Labels: a.Labels, Annotations: a.Annotations})
		log.Printf("alert %s status=%s service=%s failure_mode=%s runbook=%s",
			a.Labels["alertname"], a.Status, a.Labels["service"],
			a.Labels["failure_mode"], a.Annotations["runbook_url"])
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"received":true}`))
}

func handleAlerts(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.List())
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/webhook", handleWebhook)
	mux.HandleFunc("/alerts", handleAlerts)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("alert-sink listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

- [ ] **Step 7: Write `Dockerfile`**

```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 go build -o /alert-sink .

FROM gcr.io/distroless/static-debian12
COPY --from=build /alert-sink /alert-sink
EXPOSE 8080
ENTRYPOINT ["/alert-sink"]
```

- [ ] **Step 8: Verify build + tests**

Run:
```bash
cd platform/alerting/alert-sink
go test ./...
docker build -t localhost:5001/streamflix-alert-sink:dev .
```
Expected: tests PASS; image builds.

- [ ] **Step 9: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/alerting/alert-sink
git -c user.name=lakshminarayana-sys commit -m "feat(platform): alert-sink webhook receiver for StreamFlix alerts"
```

---

### Task 2: PrometheusRules + runbooks

**Files:**
- Create: `platform/alerting/rules/streamflix-alerts.yaml`
- Create: `platform/runbooks/cpu_throttle.md`
- Create: `platform/runbooks/oom_kill.md`
- Create: `platform/runbooks/pod_restart.md`
- Create: `platform/runbooks/image_pull_backoff.md`
- Create: `platform/runbooks/memory_leak.md`
- Create: `platform/runbooks/high_error_rate.md`
- Create: `platform/runbooks/high_latency.md`
- Create: `platform/runbooks/downstream_failures.md`

**Interfaces:**
- Consumes: live metrics (Global Constraints list).
- Produces: a `PrometheusRule` named `streamflix-alerts` in `observability` (label `release: kps`), group `streamflix.rules`, with 8 alerts. Each alert's `runbook_url` annotation = `https://runbooks.streamflix.local/<failure_mode_or_slug>` (a stable convention; the matching file is `platform/runbooks/<same-slug>.md`).

- [ ] **Step 1: Write `platform/alerting/rules/streamflix-alerts.yaml`**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: streamflix-alerts
  namespace: observability
  labels:
    release: kps
spec:
  groups:
    - name: streamflix.rules
      rules:
        - alert: StreamFlixHighErrorRate
          expr: |
            sum by (service) (rate(http_requests_total{code=~"5.."}[5m]))
              / sum by (service) (rate(http_requests_total[5m])) > 0.05
          for: 5m
          labels: {severity: SEV2, failure_mode: high_error_rate}
          annotations:
            summary: "High 5xx error rate on {{ $labels.service }}"
            description: "{{ $labels.service }} 5xx ratio above 5% for 5m."
            runbook_url: "https://runbooks.streamflix.local/high_error_rate"
        - alert: StreamFlixHighLatencyP95
          expr: |
            histogram_quantile(0.95,
              sum by (service, le) (rate(http_request_duration_seconds_bucket[5m]))) > 0.5
          for: 10m
          labels: {severity: SEV3, failure_mode: high_latency}
          annotations:
            summary: "High p95 latency on {{ $labels.service }}"
            description: "{{ $labels.service }} p95 latency above 500ms for 10m."
            runbook_url: "https://runbooks.streamflix.local/high_latency"
        - alert: StreamFlixDownstreamFailures
          expr: |
            sum by (service) (rate(downstream_requests_total{code=~"5..|error"}[5m]))
              / sum by (service) (rate(downstream_requests_total[5m])) > 0.1
          for: 10m
          labels: {severity: SEV3, failure_mode: dependency_timeout}
          annotations:
            summary: "Downstream call failures from {{ $labels.service }}"
            description: "{{ $labels.service }} downstream error ratio above 10% for 10m."
            runbook_url: "https://runbooks.streamflix.local/downstream_failures"
        - alert: StreamFlixCPUThrottling
          expr: |
            sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="streamflix-prod"}[5m]))
              / sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="streamflix-prod"}[5m])) > 0.25
          for: 10m
          labels: {severity: SEV3, failure_mode: cpu_throttle}
          annotations:
            summary: "CPU throttling on {{ $labels.pod }}"
            description: "{{ $labels.pod }} CPU throttled ratio above 25% for 10m."
            runbook_url: "https://runbooks.streamflix.local/cpu_throttle"
        - alert: StreamFlixOOMKilled
          expr: |
            max by (pod, container) (kube_pod_container_status_last_terminated_reason{namespace="streamflix-prod", reason="OOMKilled"}) == 1
          for: 1m
          labels: {severity: SEV2, failure_mode: oom_kill}
          annotations:
            summary: "OOMKilled container in {{ $labels.pod }}"
            description: "{{ $labels.pod }}/{{ $labels.container }} was OOMKilled."
            runbook_url: "https://runbooks.streamflix.local/oom_kill"
        - alert: StreamFlixPodCrashLooping
          expr: |
            increase(kube_pod_container_status_restarts_total{namespace="streamflix-prod"}[10m]) >= 3
          for: 2m
          labels: {severity: SEV2, failure_mode: pod_restart}
          annotations:
            summary: "Pod crash-looping: {{ $labels.pod }}"
            description: "{{ $labels.pod }} restarted >= 3 times in 10m."
            runbook_url: "https://runbooks.streamflix.local/pod_restart"
        - alert: StreamFlixImagePullBackOff
          expr: |
            max by (pod) (kube_pod_container_status_waiting_reason{namespace="streamflix-prod", reason=~"ImagePullBackOff|ErrImagePull"}) == 1
          for: 5m
          labels: {severity: SEV3, failure_mode: image_pull_backoff}
          annotations:
            summary: "ImagePullBackOff: {{ $labels.pod }}"
            description: "{{ $labels.pod }} cannot pull its image for 5m."
            runbook_url: "https://runbooks.streamflix.local/image_pull_backoff"
        - alert: StreamFlixMemoryNearLimit
          expr: |
            sum by (pod) (container_memory_working_set_bytes{namespace="streamflix-prod", container!=""})
              / sum by (pod) (kube_pod_container_resource_limits{namespace="streamflix-prod", resource="memory"}) > 0.9
          for: 15m
          labels: {severity: SEV3, failure_mode: memory_leak}
          annotations:
            summary: "Memory near limit: {{ $labels.pod }}"
            description: "{{ $labels.pod }} working set above 90% of its memory limit for 15m."
            runbook_url: "https://runbooks.streamflix.local/memory_leak"
```

- [ ] **Step 2: Validate the rule YAML structure offline**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai
python3 -c "import yaml,sys; d=yaml.safe_load(open('platform/alerting/rules/streamflix-alerts.yaml')); g=d['spec']['groups'][0]['rules']; print('alerts:', len(g)); assert len(g)==8; modes={r['labels']['failure_mode'] for r in g}; print(sorted(modes)); assert d['metadata']['labels']['release']=='kps'"
```
Expected: `alerts: 8` and 8 distinct failure_mode values; no assertion error.

- [ ] **Step 3: Write the 8 runbooks**

Each file follows this exact template (shown for `cpu_throttle.md`; write the analogous content for each, using the per-mode values in the table below):

`platform/runbooks/cpu_throttle.md`:
```markdown
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
```

Per-mode values for the other 7 files (same template, swap the title/alert/severity/symptom/confirm/cause/mitigation):

| File | Title / Alert | Severity | Symptom one-liner | Mitigation summary |
|---|---|---|---|---|
| `oom_kill.md` | OOMKilled (oom_kill) / StreamFlixOOMKilled | SEV2 | Container terminated with reason OOMKilled | Clear fault; raise memory limit or fix leak; confirm no new OOMKilled |
| `pod_restart.md` | Crash Loop (pod_restart) / StreamFlixPodCrashLooping | SEV2 | >=3 restarts in 10m | Clear fault; inspect `kubectl logs --previous`; fix crash; confirm restarts settle |
| `image_pull_backoff.md` | ImagePullBackOff (image_pull_backoff) / StreamFlixImagePullBackOff | SEV3 | Pod cannot pull image for 5m | Fix image tag/registry; `make deploy` to restore valid image |
| `memory_leak.md` | Memory Near Limit (memory_leak) / StreamFlixMemoryNearLimit | SEV3 | Working set >90% of memory limit for 15m | Clear fault; restart pod; raise limit or fix leak |
| `high_error_rate.md` | High Error Rate (high_error_rate) / StreamFlixHighErrorRate | SEV2 | 5xx ratio >5% for 5m | Identify failing dependency; clear fault; check downstream health |
| `high_latency.md` | High Latency (high_latency) / StreamFlixHighLatencyP95 | SEV3 | p95 latency >500ms for 10m | Clear cpu/latency fault; check throttling and downstreams |
| `downstream_failures.md` | Downstream Failures (dependency_timeout) / StreamFlixDownstreamFailures | SEV3 | Downstream error ratio >10% for 10m | Identify failing downstream service; clear its fault; verify recovery |

Each runbook's `## Confirm` PromQL must match the corresponding alert `expr` from Step 1.

- [ ] **Step 4: Apply the rule and verify the operator loads it**

Run:
```bash
kubectl --context kind-streamflix apply -f platform/alerting/rules/streamflix-alerts.yaml
kubectl --context kind-streamflix -n observability get prometheusrule streamflix-alerts
# wait for operator reload, then confirm the group is in Prometheus
kubectl --context kind-streamflix -n observability port-forward svc/kps-kube-prometheus-stack-prometheus 9090:9090 >/tmp/pf.log 2>&1 &
sleep 6
curl -s 'http://localhost:9090/api/v1/rules' | python3 -c "import sys,json; d=json.load(sys.stdin); names=[r['name'] for g in d['data']['groups'] if g['name']=='streamflix.rules' for r in g['rules']]; print(names)"
kill %1 2>/dev/null
```
Expected: the PrometheusRule exists; the curl prints the 8 `StreamFlix*` alert names (operator reload can take ~30-60s).

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/alerting/rules projects/nexusgraph-ai/platform/runbooks
git -c user.name=lakshminarayana-sys commit -m "feat(platform): StreamFlix PrometheusRules + per-mode runbooks"
```

---

### Task 3: Alertmanager routing to the sink + deploy sink + `make alerts`

**Files:**
- Modify: `platform/observability/values/kube-prometheus-stack.yaml` (add `alertmanager.config`)
- Create: `platform/alerting/alert-sink/k8s.yaml` (Deployment + Service in `observability`)
- Modify: `platform/Makefile` (add `alerts` target)

**Interfaces:**
- Consumes: alert-sink image (Task 1), PrometheusRule (Task 2), running kps release `kps`.
- Produces: Alertmanager configured with a `streamflix` route → `alert-sink` webhook receiver; `alert-sink` Deployment+Service (`alert-sink.observability.svc:8080`); `make alerts` that builds+loads the sink image, deploys it, applies rules, and upgrades kps with the new Alertmanager config.

- [ ] **Step 1: Add `alertmanager.config` to the kps values file**

Append under the existing `alertmanager:` key in `platform/observability/values/kube-prometheus-stack.yaml` (keep `enabled: true`):

```yaml
alertmanager:
  enabled: true
  config:
    global:
      resolve_timeout: 5m
    route:
      receiver: "null"
      group_by: ['alertname', 'service', 'pod']
      group_wait: 10s
      group_interval: 30s
      repeat_interval: 1h
      routes:
        - receiver: "alert-sink"
          matchers:
            - severity=~"SEV1|SEV2|SEV3"
          continue: false
    inhibit_rules:
      - source_matchers: ['severity="SEV2"']
        target_matchers: ['severity="SEV3"']
        equal: ['service', 'pod']
    receivers:
      - name: "null"
      - name: "alert-sink"
        webhook_configs:
          - url: "http://alert-sink.observability.svc:8080/webhook"
            send_resolved: true
```

- [ ] **Step 2: Write `platform/alerting/alert-sink/k8s.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: alert-sink
  namespace: observability
  labels: {app: alert-sink}
spec:
  replicas: 1
  selector: {matchLabels: {app: alert-sink}}
  template:
    metadata: {labels: {app: alert-sink}}
    spec:
      containers:
        - name: alert-sink
          image: localhost:5001/streamflix-alert-sink:dev
          ports: [{containerPort: 8080}]
          readinessProbe: {httpGet: {path: /healthz, port: 8080}, initialDelaySeconds: 2}
          resources:
            requests: {cpu: "20m", memory: "16Mi"}
            limits: {cpu: "100m", memory: "64Mi"}
---
apiVersion: v1
kind: Service
metadata:
  name: alert-sink
  namespace: observability
  labels: {app: alert-sink}
spec:
  selector: {app: alert-sink}
  ports: [{port: 8080, targetPort: 8080}]
```

- [ ] **Step 3: Add `alerts` target to `platform/Makefile`**

```makefile
.PHONY: alerts
alerts:
	@docker build -t $(REG)/streamflix-alert-sink:dev alerting/alert-sink
	@docker push $(REG)/streamflix-alert-sink:dev
	@kind load docker-image $(REG)/streamflix-alert-sink:dev --name streamflix
	@kubectl --context $(CTX) apply -f alerting/alert-sink/k8s.yaml
	@kubectl --context $(CTX) -n observability rollout status deploy/alert-sink --timeout=120s
	@kubectl --context $(CTX) apply -f alerting/rules/streamflix-alerts.yaml
	@helm --kube-context $(CTX) upgrade --install kps prometheus-community/kube-prometheus-stack \
		-n observability -f observability/values/kube-prometheus-stack.yaml --wait --timeout 10m
	@echo "Alerts deployed. Alertmanager routes SEV* to alert-sink."
```
(`CTX` and `REG` are already defined at the top of the Makefile from Phase 1.)

- [ ] **Step 4: Run `make alerts` and verify the receiver is live**

Run:
```bash
cd platform && make alerts
kubectl --context kind-streamflix -n observability get pods -l app=alert-sink
kubectl --context kind-streamflix -n observability port-forward svc/kps-kube-prometheus-stack-alertmanager 9093:9093 >/tmp/pf-am.log 2>&1 &
sleep 6
curl -s http://localhost:9093/api/v2/status | python3 -c "import sys,json; c=json.load(sys.stdin)['config']['original']; print('alert-sink' in c, 'alert-sink.observability' in c)"
kill %1 2>/dev/null
```
Expected: alert-sink pod Running; the curl prints `True True` (the Alertmanager running config contains the alert-sink webhook receiver).

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/observability/values/kube-prometheus-stack.yaml \
        projects/nexusgraph-ai/platform/alerting/alert-sink/k8s.yaml \
        projects/nexusgraph-ai/platform/Makefile
git -c user.name=lakshminarayana-sys commit -m "feat(platform): route Alertmanager SEV alerts to alert-sink + make alerts"
```

---

### Task 4: Live acceptance + `make alerts-verify` + README

**Files:**
- Modify: `platform/Makefile` (add `alerts-verify` target)
- Create: `platform/alerting/README.md`

**Interfaces:**
- Consumes: everything from Tasks 1-3 (rules loaded, Alertmanager routing, alert-sink deployed).
- Produces: `make alerts-verify` (prints rule + receiver status); documented acceptance evidence.

- [ ] **Step 1: Add `alerts-verify` to `platform/Makefile`**

```makefile
.PHONY: alerts-verify
alerts-verify:
	@echo "--- PrometheusRule ---"
	@kubectl --context $(CTX) -n observability get prometheusrule streamflix-alerts
	@echo "--- alert-sink pod ---"
	@kubectl --context $(CTX) -n observability get pods -l app=alert-sink
	@echo "--- recent alerts at the sink (port-forward then curl /alerts) ---"
	@echo "Run: kubectl --context $(CTX) -n observability port-forward svc/alert-sink 18090:8080  # then curl localhost:18090/alerts"
```

- [ ] **Step 2: ACCEPTANCE — cpu_throttle fault fires an alert delivered to the sink (run for real)**

Run:
```bash
cd platform
# baseline: sink empty
kubectl --context kind-streamflix -n observability port-forward svc/alert-sink 18090:8080 >/tmp/pf-sink.log 2>&1 &
sleep 4; curl -s localhost:18090/alerts; echo " <- before"
# inject sustained cpu_throttle on playback (TTL long enough to exceed the 10m 'for', so use latency alert which is faster, OR drive error rate). Use high_error_rate via repeated faults is not direct; cpu_throttle 'for' is 10m. To observe within minutes, ALSO assert StreamFlixHighLatencyP95 (10m) — so keep the fault on and wait.
make fault SVC=playback MODE=cpu_throttle VALUE=3 TTL=1200
# wait for the rule 'for' window; poll Alertmanager + sink
for i in $(seq 1 20); do
  sleep 60
  FIRING=$(kubectl --context kind-streamflix -n observability exec deploy/alert-sink -- true 2>/dev/null; curl -s localhost:18090/alerts)
  echo "poll $i: $FIRING"
  echo "$FIRING" | grep -q "StreamFlix" && break
done
curl -s localhost:18090/alerts | python3 -m json.tool
make fault SVC=playback MODE=clear
kill %1 2>/dev/null
```
Expected: within the alert `for` window (CPUThrottling 10m; the busy-loop fault drives both throttling and p95 latency), `GET /alerts` returns at least one StreamFlix alert (`StreamFlixCPUThrottling` and/or `StreamFlixHighLatencyP95`) with `failure_mode` and a `runbook_url`. Capture the JSON.

NOTE for the implementer: the `for` windows are minutes-long by design (they mirror `alerting.py`). If you need a faster signal to prove the pipeline end-to-end, you MAY temporarily lower one rule's `for` to `1m` in a scratch copy to observe firing, but the committed rule keeps the spec windows — document whichever you did and the real captured `/alerts` output.

- [ ] **Step 3: ACCEPTANCE — oom_kill fires StreamFlixOOMKilled to the sink**

Run:
```bash
cd platform
for i in $(seq 1 12); do make fault SVC=billing MODE=oom_kill TTL=300 >/dev/null 2>&1; sleep 3; done
sleep 90
kubectl --context kind-streamflix -n observability port-forward svc/alert-sink 18090:8080 >/tmp/pf-sink2.log 2>&1 &
sleep 4
curl -s localhost:18090/alerts | python3 -c "import sys,json; a=json.load(sys.stdin); print([x['Labels'].get('alertname') for x in a])"
kill %1 2>/dev/null
```
Expected: the printed list contains `StreamFlixOOMKilled` (OOMKilled has a 1m `for`, so it fires quickly after the real OOM). Capture output.

- [ ] **Step 4: Write `platform/alerting/README.md`**

```markdown
# StreamFlix Alerting (Phase 2)

PrometheusRules fire on real cluster metrics, Alertmanager routes them to a local
alert-sink, and each alert links a runbook.

## Deploy
```bash
cd platform
make alerts          # build+load alert-sink, deploy it, apply rules, upgrade Alertmanager config
make alerts-verify   # show rule + sink status
```

## See alerts fire
```bash
make fault SVC=playback MODE=cpu_throttle VALUE=3 TTL=1200
kubectl --context kind-streamflix -n observability port-forward svc/alert-sink 18090:8080
curl localhost:18090/alerts | python3 -m json.tool     # firing StreamFlix alerts with runbook_url
make fault SVC=playback MODE=clear
```

## Alerts
StreamFlixHighErrorRate, StreamFlixHighLatencyP95, StreamFlixDownstreamFailures,
StreamFlixCPUThrottling, StreamFlixOOMKilled, StreamFlixPodCrashLooping,
StreamFlixImagePullBackOff, StreamFlixMemoryNearLimit. Each carries `severity` +
`failure_mode` (matching the incident agent's keys) and a `runbook_url` resolving to
`platform/runbooks/<slug>.md`.

## Routing
Alertmanager (kube-prometheus-stack) routes any `severity=SEV1|SEV2|SEV3` alert to the
`alert-sink` webhook (`http://alert-sink.observability.svc:8080/webhook`); SEV2 inhibits
SEV3 for the same service/pod. Phase 3 replaces the sink with the Slack mock.
```

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/Makefile projects/nexusgraph-ai/platform/alerting/README.md
git -c user.name=lakshminarayana-sys commit -m "feat(platform): alerts-verify target + alerting README + acceptance"
```

---

## Phase 2 Done = acceptance criteria (from spec §7)

1. `streamflix-alerts` PrometheusRule present; 8 rules visible in Prometheus `/rules`. (Task 2 Step 4)
2. alert-sink Running; `/alerts` returns `[]` initially. (Task 3 Step 4 / Task 4 Step 2)
3. cpu_throttle fault → StreamFlixCPUThrottling/HighLatencyP95 firing and delivered to sink with runbook_url. (Task 4 Step 2)
4. oom_kill → StreamFlixOOMKilled delivered to sink. (Task 4 Step 3)
5. Each fired alert's runbook_url maps to an existing `platform/runbooks/*.md`. (Task 2 Step 3 + Task 4)

## Self-review notes

- **Spec coverage:** alert-sink (T1), PrometheusRules + runbooks (T2), Alertmanager routing + sink deploy + make alerts (T3), live acceptance + verify + README (T4). All spec §5 components and §7 acceptance covered.
- **Alertmanager approach:** configured via kps helm values (global config), NOT an AlertmanagerConfig CR — deliberately, because the live Alertmanager's `alertmanagerConfigSelector` is `{}` with namespaced matching that would not match cross-namespace StreamFlix alerts. Documented in the plan and spec §9.
- **Honesty flag:** alert `for` windows are minutes-long (mirroring `alerting.py`); Task 4 Step 2 notes the implementer may temporarily lower a `for` to observe firing fast but must keep the committed spec windows and report what was done. OOMKilled (1m for) fires quickly so Task 4 Step 3 is the fast, decisive proof.
- **Label consistency:** `failure_mode` values match `kubernetes.py` keys (cpu_throttle/oom_kill/pod_restart/image_pull_backoff/memory_leak) plus high_error_rate/high_latency/dependency_timeout for app SLOs. `ReceivedAlert`/`AlertStore`/`NewAlertStore` names consistent across T1 and T4.
- **k8s-metric alerts** carry `pod` (service derivable from pod name); app-metric alerts carry `service`. Documented for Phase 3.
