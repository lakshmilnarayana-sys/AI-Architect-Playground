# StreamFlix Incident-Response Agent — Week 4 Project Documentation

**Cohort:** Mastering Agentic AI — May 2026 · **Week 4: AI Evaluation**
**Repository:** https://github.com/lakshmilnarayana-sys/AI-Architect-Playground
(project root: `projects/nexusgraph-ai/`)

---

## 1. What this project is

A **multi-agent incident-response system** for a fictional streaming company
("StreamFlix"), with a **rigorous evaluation framework** (the Week-4 deliverable) and a
**real Kubernetes platform** the agent operates against.

Three layers, each building on the last:

1. **The agent** — a LangGraph incident-response pipeline
   (`Triage → Diagnose → Mitigate → Resolve → Postmortem`) grounded in a knowledge graph
   of services, teams, people, on-call schedules, runbooks, and dependencies.
2. **The evaluation framework** (Week 4 focus) — a 40-case golden dataset, 12 evaluators,
   a local + LangSmith harness, a measured baseline, and named improvement targets.
3. **The real platform** — the StreamFlix graph deployed as 35 live microservices on a
   `kind` Kubernetes cluster with full observability, alerting, runbooks, Slack/Jira/on-call
   integrations, and a software catalog — so the agent can run against **live signals**, not
   just simulated data.

---

## 2. The agent under evaluation

- **Pipeline:** `src/incident/` — a LangGraph `StateGraph` with five phases and a supervisor
  that can route back to re-diagnose. Each phase is a sub-graph of focused agents
  (triage/ownership/on-call/impact, diagnose/runbook/RCA/logs/observability, mitigate,
  resolve, postmortem).
- **Grounding:** a knowledge graph (`graph/nodes.csv`, `graph/edges.csv`) of 35 services,
  13 teams, 12 people, ownership, on-call schedules, escalation policies, dependencies.
- **Determinism for evaluation:** with `INCIDENT_LIVE` unset and LLMs/Neo4j disabled, the
  pipeline uses deterministic fallbacks, making every run reproducible — essential for a
  trustworthy eval. An optional live mode (`INCIDENT_LIVE=true`) swaps in real cluster /
  Prometheus reads and real Slack/Jira/on-call calls **without changing the deterministic
  path** (additive, env-gated).
- **User outcome being measured:** an on-call engineer gets the right root cause, the right
  team/person paged, a correct failure-specific mitigation, and a faithful postmortem —
  fast enough to act on.

---

## 3. The evaluation framework (Week 4 deliverable)

Located in `evaluation/incident/`. Documented in `evaluation/incident/README.md`.

### 3.1 Golden dataset — `golden_dataset.json` (built by `build_dataset.py`)
40 hand-labeled cases:
- **20 happy (50%)** — seeded from the 23 real StreamFlix scenarios in
  `data/incident_scenarios.yaml`.
- **12 edge (30%)**, **6 known-failure (15%)**, **2 adversarial (5%)** — hand-authored
  (hyphenated service names, unmodeled failure modes, prompt-injection in the signal text).

Ground-truth labels (`labels.py`) are verified against `graph/edges.csv`,
`data/escalation_policies.yaml`, and the `mitigate.py` templates.

### 3.2 Evaluators — `evaluators.py` (10 code-based + 2 LLM-as-judge)
| Evaluator | What it checks | Method |
|---|---|---|
| `failure_mode_accuracy` | RCA identifies the right failure mode | exact match |
| `owning_team_accuracy` | correct owning team resolved | exact match |
| `escalation_accuracy` | correct escalation policy | exact match |
| `oncall_paged` | the right on-call schedule/person paged | match |
| `mitigation_correctness` | mitigation contains the right keyphrases | keyphrase |
| `task_completion` | pipeline reaches postmortem | trajectory |
| `no_crash` | no unhandled exception | trajectory |
| `rediagnose_trajectory` | re-diagnoses when first attempt is wrong | counter (`_diagnose_attempts`) |
| `no_injection_leak` | adversarial signal text doesn't alter actions | string check |
| `latency_seconds` | wall-clock per case | timing |
| `rca_faithfulness` *(LLM judge)* | RCA grounded in evidence, no hallucination | LLM-as-judge |
| `postmortem_faithfulness` *(LLM judge)* | postmortem grounded in the timeline | LLM-as-judge |

Code-based evaluators are pure functions; LLM judges are optional
(`INCIDENT_USE_LLM=true`). The same evaluators run locally and via LangSmith.

### 3.3 Harnesses
- `run_local.py` — runs all 40 cases and writes `baseline_local.json`. No account needed.
- `run_agent.py` — `run_incident_target(inputs)` maps a dataset row through the pipeline and
  returns a flat, scorable dict (de-duplicates timeline/logs/observability so trajectory
  metrics are accurate).
- `upload_dataset.py` / `run_langsmith.py` — push the dataset and run `client.evaluate` in
  LangSmith for full traces + token/latency cost (`LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`).

### 3.4 Baseline results (40 cases, deterministic)
```
failure_mode_accuracy    1.000   ✅ (bar 0.95)
owning_team_accuracy     0.950   ✅ (bar 0.95)
mitigation_correctness   0.975   ✅ (bar 0.90)
no_injection_leak        1.000   ✅
rediagnose_trajectory    0.975   ✅
task_completion          0.970   ⚠️ (bar 1.00 — 1 unmodeled-mode crash)
escalation_accuracy      0.525   ❌ (bar 0.90)
oncall_paged             0.025   ❌ (bar 0.90)
latency                  ~0.08s mean, p95 ≈0.12s   ✅ (bar <90s)
```

### 3.5 Failure analysis & improvement targets
Three clear failure clusters (the Day-4 work):
1. **On-call person never resolved** — `oncall_for` returns a schedule name, not a person;
   the registry/graph lookup needs a person-resolution step.
2. **Escalation brittle on hyphenated names** — `service.split()[0]` tokenization breaks for
   names like `payment-gateway-service`.
3. **Unmodeled-mode crash** — a failure mode with no modeled K8s resource raises instead of
   degrading gracefully.

These are reproducible, code-checked, and traceable in LangSmith — the eval framework's
purpose is exactly to surface and track them.

---

## 4. The real platform (StreamFlix on Kubernetes)

Built in four phases under `platform/`; full specs/plans in `docs/superpowers/`. Everything
is generated from the same `graph/*.csv` (single source of truth) and runs on a local `kind`
cluster.

| Phase | Delivered | Verified |
|---|---|---|
| **1 — Services + observability** | 35-service Go topology generated from the graph; Prometheus/Grafana/Loki/Tempo; loadgen; fault injection; OpenTelemetry trace fan-out | 1 trace = 19 services / 427 spans in Tempo |
| **2 — Alerting + runbooks** | 8 PrometheusRules on real metrics → Alertmanager → alert sink; per-mode runbooks | injected fault → real `StreamFlixOOMKilled`/`CPUThrottling` delivered |
| **3 — Integrations + live loop** | Slack/Jira/on-call mocks; agent reads live cluster + Prometheus (`INCIDENT_LIVE`); watcher polls Alertmanager and runs the pipeline | manual run created Jira `INC-167161` + resolved on-call; watcher ran the agent for 35 live alerts |
| **4 — Software catalog** | Backstage entity model (1 System / 13 Groups / 12 Users / 35 Components, `dependsOn`/`ownedBy` + Prometheus/runbook annotations) generated from the graph, served via catalog API | live API returns 35/13/12 |

**Honest limitation:** the full Backstage **UI** was not built in this environment (host
Node 25 / no yarn; create-app interactivity + Yarn 4 strict lockfile). A lightweight Go
`catalog-server` serves the *same* generated entities at `/api/catalog/entities` — documented
in `platform/backstage/README.md`.

---

## 5. Architecture

```
                         graph/{nodes,edges}.csv   ← single source of truth
                                   │
        ┌──────────────────────────┼───────────────────────────────┐
        ▼                          ▼                                ▼
  35 microservices          incident agent                 Backstage catalog
  (kind cluster)            (src/incident, LangGraph)       (61 entities)
        │                          │
   Prometheus/Grafana        evaluation framework
   Loki/Tempo                (evaluation/incident: 40 cases, 12 evaluators)
        │                          │
   8 PrometheusRules ─► Alertmanager ─► slack-mock / jira-mock / on-call registry
                                   ▲
                          watcher polls Alertmanager → runs the pipeline on firing alerts
```

The agent is the same whether evaluated (deterministic) or run live (`INCIDENT_LIVE=true`).

---

## 6. How to run

### Evaluation (no external dependencies)
```bash
cd projects/nexusgraph-ai
/opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m evaluation.incident.run_local            # 40 cases → baseline_local.json
INCIDENT_USE_LLM=true python -m evaluation.incident.run_local   # + LLM-judge faithfulness
```

### LangSmith (full traces + cost)
```bash
export LANGSMITH_API_KEY=...  LANGSMITH_TRACING=true
python -m evaluation.incident.upload_dataset
python -m evaluation.incident.run_langsmith --prefix baseline
```

### The live platform (optional, requires Docker + kind + kubectl + helm)
```bash
cd platform
make up && make observe && make build deploy   # cluster + observability + 35 services
make alerts && make incident-services           # alerting + Slack/Jira/on-call mocks
make backstage                                   # software catalog
make fault SVC=playback MODE=cpu_throttle        # inject a fault, watch it flow end-to-end
```

---

## 7. Repository map

```
projects/nexusgraph-ai/
  src/incident/          # the multi-agent pipeline (agent under test)
  evaluation/incident/   # ← Week 4 deliverable: dataset, evaluators, harnesses, baseline
  graph/                 # the knowledge graph (single source of truth)
  data/                  # scenarios, runbooks, on-call, escalation, SLO ground truth
  platform/              # the real Kubernetes platform (Phases 1–4)
    services/ alerting/ incident-services/ backstage/ runbooks/
  docs/superpowers/      # per-phase specs + implementation plans
  README.md              # full project README
  PROJECT_DOCUMENTATION.md  # this file
```

---

## 8. Summary

This project takes a multi-agent incident-response system from a deterministic simulation to
a **measured, evaluated agent running against a real Kubernetes platform**. The Week-4
deliverable — the evaluation framework — provides a reproducible 40-case golden dataset, 12
evaluators spanning quality/behavior/cost, a measured baseline, and three concrete,
traceable improvement targets. The surrounding platform makes the agent's signals real
(live cluster, Prometheus, alerting, Slack/Jira/on-call, software catalog), and every live
capability is additive and env-gated so the evaluation remains deterministic and trustworthy.
