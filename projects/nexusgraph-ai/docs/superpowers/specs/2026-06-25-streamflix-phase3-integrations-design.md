# StreamFlix Platform Phase 3 — Integrations + Live Incident Loop (Design)

**Date:** 2026-06-25
**Status:** Approved (design) — proceeding to plan
**Builds on:** Phase 1 (cluster + 35 services + observability), Phase 2 (PrometheusRules → Alertmanager → alert-sink), gap closeout (OTel traces).

## 1. Goal

Close the real incident loop: a firing Alertmanager alert drives the existing incident
agent to run against **live** cluster + Prometheus signals, resolve on-call from a real
**on-call registry**, post the incident thread to a real **Slack mock**, and open a real
**Jira mock** ticket — all locally, nothing leaving the machine.

## 2. Current state (what we replace)

- `src/incident/slack.py` — in-memory message rendering only (no API).
- `src/incident/jira.py` — writes a local YAML file with deterministic `INC-xxxxxx` keys.
- `src/incident/kubernetes.py` — reads a static `data/kubernetes_resources.yaml`.
- `src/incident/observability.py` — returns static evidence.
- `src/incident/graph_lookup.py` — `oncall_for`/`escalation_for` traverse CSV/YAML.
- Runs are triggered manually in tests; no alert-driven kickoff.

## 3. Decisions (confirmed)

| Decision | Choice |
|---|---|
| Agent runtime | **Local Python process**, reaches cluster via kubectl context + port-forward to in-cluster mocks. |
| Liveness | **Full live**: kubernetes.py + observability.py read the real cluster/Prometheus; Slack/Jira/on-call go through real local mock services. |
| Trigger | **Auto from alert (local watcher polls Alertmanager) + manual CLI**. |
| Mock language | **Go** (consistent with alert-sink; tiny images). On-call data mounted via ConfigMap. |
| slack-mock vs alert-sink | slack-mock **replaces** alert-sink as Alertmanager's receiver (the planned Phase-2 evolution). |

## 4. Guiding principle: additive live providers with fallback

Every integration is a **live provider gated by `INCIDENT_LIVE=true`**, with the current
deterministic behavior as the fallback (mirrors the existing `GraphContext` Neo4j/CSV
pattern). Tests and evals keep `INCIDENT_LIVE` unset → fully deterministic and
reproducible. Live mode degrades gracefully to fallback on any cluster/mock error.

## 5. Components

### 5.1 In-cluster mock services (`platform/incident-services/`, Go)

Each: tiny Go service, image `localhost:5001/streamflix-<name>:dev`, Deployment+Service in
`observability` (reached from the local agent via `kubectl port-forward`).

- **slack-mock** (`slack-mock:8080`):
  - `POST /webhook` — Alertmanager webhook receiver (replaces alert-sink); stores alerts.
  - `POST /api/chat.postMessage` — body `{channel, text, username}` → returns `{ok:true, ts, channel}` with a realistic incrementing `ts`.
  - `GET /channels/{name}` — messages for a channel (newest first); `GET /alerts` — received alerts.
- **jira-mock** (`jira-mock:8080`):
  - `POST /rest/api/2/issue` — body `{fields:{summary, ...}}` → `{key:"INC-xxxxxx", id, self}`; key derived deterministically (sha1 of incident id, matching `jira.py._issue_key`) when `incident_id` is supplied, else sequential.
  - `GET /rest/api/2/issue/{key}` and `GET /issues` — retrieve.
- **oncall-registry** (`oncall-registry:8080`):
  - `GET /oncall/{service}` → `{service, schedule, person, team}`.
  - `GET /escalation/{service}/{severity}` → `{policy, steps}`.
  - `GET /schedules` → all. Data loaded at boot from a mounted JSON file.

### 5.2 On-call registry data (`platform/incident-services/oncall-registry/seed/`)

A Python generator reads `data/oncall_schedules.yaml`, `escalation_policies.yaml`,
`people.yaml`, `teams.yaml`, and `graph/edges.csv` (OWNS_SERVICE) and emits
`oncall-seed.json` (service → {schedule, person, team}; service+severity → policy). The
JSON is mounted into oncall-registry via a ConfigMap. This keeps the registry's answers
aligned with the incident agent's existing ground truth.

### 5.3 Agent live providers (modify `src/incident/`)

All gated by `INCIDENT_LIVE` + endpoint env vars; deterministic fallback unchanged.

- `kubernetes.py` — `live_runtime(service)` reads real pod/workload status + events for the
  affected service via the k8s API (`kubectl get pod -o json` / events) and maps to the
  same runtime dict shape `inject_failure`/`healthy_runtime` produce (so downstream phases
  are unchanged). Detects active failure from real symptoms (OOMKilled, CrashLoopBackOff,
  ImagePullBackOff, restart delta).
- `observability.py` — `live_evidence(service, failure_mode)` queries real Prometheus
  (`http://localhost:<pf>/api/v1/query`) for the service's error-rate/p95/throttle and
  returns evidence items in the existing shape.
- `slack.py` — `post_to_slack(channel, message)` POSTs to slack-mock `/api/chat.postMessage`
  (returns real ts); keeps `event_to_slack_message` rendering. Fallback: in-memory.
- `jira.py` — `create_issue_live(state)` POSTs to jira-mock; falls back to the YAML store.
  Deterministic key scheme preserved.
- `graph_lookup.py` — `oncall_for`/`escalation_for` query oncall-registry first (when live),
  then fall back to CSV/YAML.

A small `src/incident/live_clients.py` holds the HTTP client + endpoint resolution
(`SLACK_MOCK_URL`, `JIRA_MOCK_URL`, `ONCALL_REGISTRY_URL`, `PROMETHEUS_URL`,
`KUBE_CONTEXT`) so the providers stay thin and testable.

### 5.4 Trigger — `src/incident/watcher.py` + run entrypoint

- **Watcher:** polls Alertmanager `/api/v2/alerts?active=true` (via port-forward). For each
  new firing alert with a StreamFlix `alertname`, dedupes by fingerprint, maps the
  `service`/`failure_mode` labels to an incident seed, and invokes the pipeline. Idempotent
  (won't re-run the same fingerprint while active).
- **Manual CLI:** `python -m src.incident.run --service playback-service [--failure-mode oom_kill]`
  builds an incident seed and runs the pipeline once against live data.

### 5.5 Makefile / UX

- `make incident-services` — generate oncall seed, build+`kind load` the 3 images, apply
  ConfigMap + manifests, point Alertmanager at slack-mock (helm values receiver URL →
  `http://slack-mock.observability.svc:8080/webhook`), rollout.
- `make incident-up` — port-forward slack-mock/jira-mock/oncall-registry/Alertmanager/
  Prometheus and start the watcher (prints the env exports the agent needs).
- `make incident-verify` — show the 3 pods + how to read their GET endpoints.

## 6. Acceptance criteria (the "real loop" test)

1. The 3 mock pods Running; oncall-registry `GET /oncall/billing-service` returns the
   schedule/person/team matching the graph ground truth.
2. Alertmanager receiver is slack-mock; a firing alert appears at slack-mock `GET /alerts`.
3. `python -m src.incident.run --service billing-service` with `INCIDENT_LIVE=true` runs
   end-to-end: reads live cluster runtime, posts an incident thread to slack-mock
   (`GET /channels/...` shows it), creates a jira-mock issue (`GET /issues` shows
   `INC-xxxxxx`), and resolves on-call from the registry.
4. **Full loop:** inject `oom_kill` on billing → `StreamFlixOOMKilled` fires → slack-mock
   receives the alert → watcher runs the agent → live OOMKilled detected, Slack thread +
   Jira ticket created, on-call resolved — all verifiable via the mocks' GET endpoints.
5. With `INCIDENT_LIVE` unset, the existing incident eval/tests still pass (deterministic
   fallback intact).

## 7. Non-goals (Phase 3)

No Backstage (Phase 4); no real Slack/Jira SaaS; no PagerDuty/real paging; agent stays a
local process (not containerized). Live providers are env-gated; deterministic fallback is
the default for tests/evals.

## 8. Risks & mitigations

- **Breaking the eval suite** → all live behavior behind `INCIDENT_LIVE`; fallback paths
  unchanged; a regression test asserts deterministic output when the flag is unset.
- **Port-forward churn** → `make incident-up` centralizes forwards; clients read endpoint
  env vars with sane localhost defaults.
- **Live k8s/Prometheus shape drift** → live providers normalize into the EXISTING runtime/
  evidence dict shapes so downstream phases need no changes.
- **Watcher double-firing** → dedupe by Alertmanager fingerprint; only act on `active` +
  StreamFlix alertnames.
