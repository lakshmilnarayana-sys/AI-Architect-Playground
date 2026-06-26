# Video Demo Script — StreamFlix Incident-Response Agent (Week 4)

**Target length:** 2.5–3 minutes. **Format:** screen recording + voiceover.
**Goal:** show (1) the Week-4 evaluation framework, then (2) the live incident loop it
measures. Record at 1080p; keep the terminal font large.

**Before you hit record (setup, off-camera):**
```bash
cd projects/nexusgraph-ai && source .venv/bin/activate
# make sure the cluster is up if you want to show the live loop:
#   cd platform && make up observe deploy alerts incident-services backstage   (already running in your session)
# have two terminals + a browser tab ready (Grafana on :3000)
```

---

## Scene 1 — Hook + what it is (0:00–0:25)

**On screen:** the repo README (top section) or the architecture diagram in
`PROJECT_DOCUMENTATION.md` §5.

**Say:**
> "This is a multi-agent incident-response system for a fictional streaming company,
> StreamFlix. A LangGraph pipeline — triage, diagnose, mitigate, resolve, postmortem —
> grounded in a knowledge graph of services, teams, on-call, and runbooks. For Week 4 I
> built a full evaluation framework around it, and I run it against a *real* Kubernetes
> platform. Let me show both."

---

## Scene 2 — The evaluation framework (0:25–1:15) — THE WEEK 4 DELIVERABLE

**On screen:** `evaluation/incident/` in the editor; briefly show `golden_dataset.json`
and `evaluators.py`, then run the harness.

**Say:**
> "The eval has a 40-case golden dataset — 50% happy, 30% edge, 15% known-failure, 5%
> adversarial — seeded from 23 real incident scenarios. Twelve evaluators: ten code-based
> for everything machine-checkable, plus two LLM-as-judge for faithfulness. It runs
> locally, no account needed."

**Do (record the run):**
```bash
python -m evaluation.incident.run_local
```

**Say (over the output):**
> "Forty cases, deterministic. Failure-mode accuracy 100%, owning-team 95%, mitigation 97%,
> no injection leaks. And it honestly surfaces the gaps — escalation and on-call paging are
> low: those are my three failure-analysis targets — on-call returns a schedule not a
> person, escalation breaks on hyphenated service names, and one unmodeled failure mode
> crashes. The point of the eval is to make those reproducible and trackable."

---

## Scene 3 — The agent running live (1:15–2:20)

**On screen:** terminal + Grafana tab.

**Say:**
> "The same agent can run against a real cluster. Here are 35 StreamFlix microservices on a
> local Kubernetes cluster with full observability."

**Do — inject a fault:**
```bash
cd platform
make fault SVC=billing MODE=oom_kill TTL=300
```

**Say:**
> "I'm injecting a real OOM kill into the billing service."

**Do — show it propagate (switch to Grafana, then the mocks):**
```bash
# in another terminal, after ~1 min:
kubectl --context kind-streamflix -n streamflix-prod get pods -l app=billing-service
# show the OOMKilled, then the alert reached the sink and the agent ran:
curl -s localhost:18100/alerts | python3 -m json.tool | head
curl -s localhost:18101/issues | python3 -m json.tool | head
curl -s localhost:18102/oncall/billing-service
```

**Say (over it):**
> "The pod is OOMKilled — that's a real Kubernetes event, and Kubernetes restarts the pod on
> its own. But restarting the symptom isn't incident response. Here's what the AI agent does
> on top of that."

**Do — launch the LIVE DASHBOARD (THE 'where's the AI' moment — one terminal, 4 panes):**
```bash
INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 \
ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 \
ALERTMANAGER_URL=http://localhost:9093 KUBE_CONTEXT=kind-streamflix \
.venv/bin/python -m src.incident.demo_dashboard --service billing-service --failure-mode oom_kill
```
Panes: 🤖 Agent Reasoning (streams in) · ☸ Kubernetes & Metrics (live pod status + p95) ·
🔌 Integrations (Slack channel, Jira ticket, on-call appear as the agent creates them).
Plain non-dashboard alternative: `.venv/bin/python -m src.incident.print_trace --service billing-service --failure-mode oom_kill --demo`

**Say (scroll the trace):**
> "Twenty-three steps across six phases. It confirms severity, finds the owning team and
> pages on-call, reads the live Kubernetes context, pulls the Billing runbook, forms a
> root-cause hypothesis — OOM kill — proposes a concrete mitigation: raise the memory limit,
> roll a canary, drain the OOMKilled pods, verify restarts stabilize. Then it verifies the
> SLO recovered, drafts the postmortem with a human-approval gate, and opens the Jira
> ticket. Same agent, real signals — and because live mode is env-gated, the evaluation
> stays fully deterministic."

**Do — show the evidence it produced:**
```bash
curl -s localhost:18101/issues | python3 -m json.tool | head     # the Jira ticket it opened
curl -s localhost:18102/oncall/billing-service                   # on-call it resolved
```

---

## Scene 4 — Software catalog + close (2:20–2:50)

**On screen:** the catalog API response.

**Do:**
```bash
curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=component' \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),"components in the catalog")'
```

**Say:**
> "Finally, a software catalog — 35 components with their owners, dependencies, and runbook
> links — all generated from the same graph that drives everything else. So: a measured,
> evaluated agent, running on a real platform, with one source of truth. Thanks for
> watching."

---

## Recording tips
- **Pre-run** the slow commands once before recording so images are cached and output is fast.
- If the OOM/alert timing is slow on camera, **cut** between "inject" and "show result" — or
  narrate over the wait. The eval run (Scene 2) and the catalog (Scene 4) are instant and are
  your guaranteed-clean shots.
- Keep it to ~3 min. The two must-show moments are **the eval baseline output** and **the
  fault → agent → Jira/Slack loop**.
- Upload to Google Drive, set "Anyone with the link → Viewer," and paste that link into the
  form's *Video Demo Drive Link* field.
