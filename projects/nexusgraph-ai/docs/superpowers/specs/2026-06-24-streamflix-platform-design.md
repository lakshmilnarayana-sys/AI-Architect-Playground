# StreamFlix Platform — Real Kubernetes Deployment (Design)

**Date:** 2026-06-24
**Status:** Approved (design) — pending spec review
**Author:** Lakshmi Narayana Vommi (with Claude)

## 1. Goal

Make the *imaginary* StreamFlix world that already lives in `nexusgraph-ai/graph/`
**real**: actual microservices running on a real Kubernetes cluster, emitting real
metrics/logs/traces, with controllable failures that reproduce the incident agent's
documented failure modes — plus (in later phases) alerting, runbooks, Slack/Jira,
an on-call registry, and a Backstage software catalog. The end state lets the
existing incident-response agent operate against **live signals** instead of
deterministic fallbacks.

This is a **platform**, decomposed into 4 phases. This document specifies **Phase 1**
in full and outlines Phases 2–4. Each later phase gets its own spec → plan → execution.

## 2. Existing assets we build on (additive, do not reinvent)

- `nexusgraph-ai/graph/nodes.csv` — 10 services, 6 teams, 12 people, projects, skills.
- `nexusgraph-ai/graph/edges.csv` — ownership + people edges. **No service→service
  dependency edges yet** (we add them, see §4.3).
- `nexusgraph-ai/src/incident/` — LangGraph incident agent (Triage→Diagnose→Mitigate→
  Resolve→Postmortem) with `jira.py`, `slack.py`, `alerting.py`, `kubernetes.py`,
  `observability.py`, `logs.py`.
- `nexusgraph-ai/data/kubernetes_resources.yaml` — per-service workloads + the **8
  failure modes**, namespace `streamflix-prod`, cluster `streamflix-prod-use1`.
- `nexusgraph-ai/src/incident/kubernetes.py` — `inject_failure` / `available_failure_modes`.
  The 8 modes: `oom_kill`, `pod_restart`, `disk_iops`, `cpu_throttle`, `memory_leak`,
  `node_pressure`, `image_pull_backoff`, `hpa_maxed`.

**Single source of truth:** the graph CSVs. The cluster is *generated from* the graph,
so the running system always matches the incident agent's ground truth.

## 3. Decisions (confirmed)

| Decision | Choice | Why |
|---|---|---|
| Target cluster | **Local `kind`** on the Mac (64GB/16CPU) | Isolated, free, disposable; never touches the real `*-prod` EKS clusters. |
| Service realization | **A — one parameterized Go service, deployed 10×** | Real topology/telemetry/failures, names match graph ground truth, ~one codebase. |
| Slack/Jira | **Simulated locally** | Nothing leaves the Mac; reproducible; pluggable to real tokens later. |
| Sequencing | **Phase 1 first**, approve each phase | Too much for one safe deploy. |
| Service language | **Go** | Tiny footprint at 10+ replicas; builds in-container (no local Go toolchain). |

## 4. Phase 1 architecture — cluster + services + observability

### 4.1 Cluster

- `kind` cluster `streamflix`: 1 control-plane + 2 workers.
- Local image registry (`kind-registry`, `localhost:5001`) so we push the service image
  without a remote registry. Wired via the standard kind+registry containerd patch.
- Namespaces: `streamflix-prod` (apps — matches `kubernetes_resources.yaml`),
  `observability`.
- Prereqs handled at execution: Docker Desktop running; install `kind` (absent now;
  `kubectl`+`helm` present).

### 4.2 Service template (`platform/services/streamflix-service`, Go)

One image, configured per-service via env/ConfigMap. Endpoints:

- `GET /` — does simulated work (configurable base latency + CPU cost), then fans out to
  its downstream dependencies (HTTP) per config, aggregates, returns. Propagates trace
  context.
- `GET /healthz`, `GET /readyz` — liveness/readiness.
- `GET /metrics` — Prometheus: `http_requests_total{service,code}`,
  `http_request_duration_seconds` (histogram), `downstream_requests_total{target,code}`,
  `app_inflight_requests`, plus Go runtime metrics.
- `POST /admin/fault` — inject/clear a fault at runtime (body: `{mode, value, ttl}`).
- Emits OTel traces (OTLP → collector) and structured JSON logs to stdout.

**Env contract (set by generator from the graph):**
`SERVICE_NAME`, `SERVICE_TIER` (customer-facing|internal), `DOWNSTREAMS` (comma list of
`name=url`), `BASE_LATENCY_MS`, `ERROR_RATE`, `OTEL_EXPORTER_OTLP_ENDPOINT`.

### 4.3 Topology generator (`platform/scripts/generate_manifests.py`)

Reads `graph/nodes.csv` + `graph/edges.csv` and renders, per service, a Deployment +
Service + ConfigMap into `platform/cluster/generated/`. Customer-facing services get the
loadgen pointed at them.

**We add `DEPENDS_ON` edges to `edges.csv`** (the missing topology), giving StreamFlix a
realistic dependency graph that the generator and the incident agent's blast-radius logic
both read:

```
service:playback      DEPENDS_ON service:manifest
service:playback      DEPENDS_ON service:cdn-routing
service:playback      DEPENDS_ON service:recommendation
service:playback      DEPENDS_ON service:identity
service:manifest      DEPENDS_ON service:cdn-routing
service:recommendation DEPENDS_ON service:feature-store
service:billing       DEPENDS_ON service:payment-gateway
service:billing       DEPENDS_ON service:identity
service:payment-gateway DEPENDS_ON service:identity
service:audit-evidence DEPENDS_ON service:identity
# every service DEPENDS_ON service:observability (telemetry sink)
```

### 4.4 Failure modes → real Kubernetes mechanisms

The `/admin/fault` API plus per-service manifest variants reproduce the 8 modes as
**genuine** K8s/runtime symptoms the incident agent can later read live:

| Mode | Mechanism | Real symptom |
|---|---|---|
| `oom_kill` | low `memory` limit + balloon allocation via fault | `OOMKilled`, restart count ↑ |
| `pod_restart` | fault exits process (code 137) | `CrashLoopBackOff` |
| `cpu_throttle` | low `cpu` limit + busy-loop fault | CPU throttling metrics ↑, latency ↑ |
| `memory_leak` | fault grows RSS gradually | `MemoryPressure`, RSS slope |
| `hpa_maxed` | HPA `maxReplicas` low + CPU-driving fault | `HPAMaxedOut`, desired>max |
| `image_pull_backoff` | deploy variant with bad image tag | `ImagePullBackOff` |
| `node_pressure` | memory-balloon fault across pods → eviction | `NodePressure`/`Evicted` (best-effort) |
| `disk_iops` | fault adds I/O latency on a mounted volume | `VolumeLatencyHigh` (simulated metric) |

`node_pressure` and `disk_iops` are best-effort/simulated on a laptop kind cluster; the
other six are genuinely reproducible. This is documented honestly, not papered over.

### 4.5 Traffic generator (`platform/services/loadgen`)

A small Deployment that continuously hits the customer-facing entrypoints (playback,
billing, identity, recommendation, manifest, cdn-routing, payment-gateway) at a steady
RPS so dashboards show real baseline traffic and faults produce visible deltas.

### 4.6 Observability stack (Helm, `observability` ns)

- `kube-prometheus-stack` — Prometheus + Alertmanager + Grafana + kube-state-metrics +
  node-exporter.
- `loki` + `promtail` — logs.
- `tempo` + OpenTelemetry Collector — traces (OTLP in, Tempo out).
- Grafana datasources (Prometheus/Loki/Tempo) auto-provisioned; `ServiceMonitor`s scrape
  the app `/metrics`. Access via `kubectl port-forward` (documented in Makefile).

### 4.7 Repository layout

```
nexusgraph-ai/platform/
  Makefile                 # up / down / build / deploy / observe / fault / verify
  cluster/
    kind-config.yaml
    registry.sh
    generated/             # generator output (git-ignored or committed snapshot)
  services/
    streamflix-service/    # Go template (Dockerfile multi-stage)
    loadgen/
  observability/
    values/                # helm values for prometheus-stack, loki, tempo, otel
    install.sh
  scripts/
    generate_manifests.py
```

### 4.8 Makefile / UX

`make up` (kind+registry) → `make build` (image→registry) → `make observe` (helm
installs) → `make deploy` (generate+apply apps+loadgen) → `make verify` →
`make fault SVC=playback MODE=cpu_throttle` → `make down`.

## 5. Phase 1 acceptance criteria (the "is it real" test)

1. `kubectl get pods -A` — all StreamFlix + observability pods `Running`.
2. Grafana shows per-service RPS / latency / error-rate from real scrapes.
3. A trace for a `playback` request shows the fan-out to its real downstreams in Tempo.
4. Loki shows structured logs from the services.
5. `make fault SVC=playback MODE=cpu_throttle` → **visible latency/throttle spike in
   Grafana within ~1 min**; `make fault ... MODE=clear` returns to baseline.
6. `make fault SVC=billing MODE=oom_kill` → real `OOMKilled` event in
   `kubectl describe pod`.

## 6. Later phases (outline — separate specs)

- **Phase 2 — Alerting + runbooks:** PrometheusRules for the 8 modes (high latency,
  error budget burn, OOM, CrashLoop, HPA maxed…), Alertmanager routing, and runbooks in
  `platform/runbooks/` linked from alert annotations (`runbook_url`).
- **Phase 3 — Integrations + incident loop:** local Slack & Jira mock services (HTTP
  endpoints + a webhook sink UI), an on-call registry (seeded from the graph
  people/teams + schedules), and wiring `src/incident/{kubernetes,observability,alerting,
  slack,jira}.py` to the **live** cluster/Prometheus/Alertmanager so an injected fault
  drives a real end-to-end incident.
- **Phase 4 — Software catalog (Backstage):** Backstage deployed in-cluster, catalog
  entities (Components/Systems/Groups/Users) generated from the same graph CSVs, TechDocs
  for runbooks. Pluggable to the real Slack/Jira tokens via secrets when desired.

## 7. Non-goals / YAGNI (Phase 1)

- No real cloud cluster, no real Slack/Jira, no Backstage, no alert routing yet.
- No persistence/databases for services (stateless simulators).
- No ingress/TLS — access via port-forward.
- No multi-language services (one Go template, replicated).

## 8. Risks & mitigations

- **Docker not running / kind absent** → execution step checks Docker, installs kind.
- **Resource pressure** (10 services + full obs stack) → modest replica counts (1 each),
  tuned Helm values; 64GB is ample.
- **`node_pressure`/`disk_iops` not fully real on a laptop** → documented as simulated;
  the other 6 modes are genuine.
- **Generator drift from graph** → generator is the only path that writes manifests;
  `make deploy` always regenerates.
