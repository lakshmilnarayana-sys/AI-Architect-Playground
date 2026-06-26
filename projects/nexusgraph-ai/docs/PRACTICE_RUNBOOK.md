# Practice Runbook — StreamFlix Demo (start services + trigger the incident)

Use this to rehearse before recording. The cluster is normally already running; you mostly
**open dashboards and trigger faults**, not bring the stack up from scratch.

Two flavors of "incident simulation" — your demo wants both:
- **Path A — the agent itself** (instant, deterministic, always clean): the agent reasons
  through triage→diagnose→mitigate→resolve→postmortem. This is the eval / `src.incident.run`.
- **Path B — the live loop** (the wow): inject a real fault → Prometheus alert fires → the
  agent runs against live signals → posts to Jira/Slack/on-call mocks.

---

## 0. Confirm it's up (10s)
```bash
kubectl --context kind-streamflix -n streamflix-prod get pods | tail -3   # Running
```
Expected: 36 app pods + 20 observability/mock pods + 1 Backstage, all Running. No `make up` needed.

## 1. Open dashboards (each in its own terminal tab)
```bash
# Grafana:
kubectl --context kind-streamflix -n observability port-forward svc/kps-grafana 3000:80
#   → http://localhost:3000   (admin / admin)

# Mocks + Prometheus + Alertmanager + the agent env line (from platform/):
cd projects/nexusgraph-ai/platform && make incident-up
```

> **IMPORTANT — your Mac has no bare `python`.** Always use `.venv/bin/python`, and run the
> agent from the **nexusgraph-ai root** (NOT `platform/`), or `src.incident` won't import.
> All paths below are relative to `~/Documents/maven/projects/nexusgraph-ai`.

## 2. Path A — run the agent (deterministic; clean opener for the video)
```bash
cd ~/Documents/maven/projects/nexusgraph-ai
.venv/bin/python -m evaluation.incident.run_local                              # 40-case eval
.venv/bin/python -m src.incident.run --service billing-service --failure-mode oom_kill   # single (deterministic)
```

## 3. Path B — the live loop (RELIABLE: manual run, no waiting on alerts)
From the nexusgraph-ai root. This ONE command runs the agent live and always creates a Jira
ticket + Slack post (env vars are inline — no separate export step to forget):
```bash
cd ~/Documents/maven/projects/nexusgraph-ai
INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 \
ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 \
ALERTMANAGER_URL=http://localhost:9093 KUBE_CONTEXT=kind-streamflix \
.venv/bin/python -m src.incident.run --service billing-service --failure-mode oom_kill --severity SEV2
#   → prints: jira: INC-xxxxxx

# show the evidence in the mocks:
curl -s localhost:18101/issues | python3 -m json.tool                                       # Jira ticket
curl -s "localhost:18100/channels/inc-manual-incident-on-billing-service" | python3 -m json.tool   # Slack thread
curl -s localhost:18102/oncall/billing-service        # on-call: team+schedule (person:"" = KNOWN eval gap, mention it!)
```

### ⭐ One-command LIVE DASHBOARD (recommended for the recording)
Splits ONE terminal into a header + 4 live panes — agent reasoning streaming in, live
Kubernetes pod status + a **p95 sparkline (peak→now)**, the Slack/Jira/on-call integrations,
and a **Status Page** with a HITL approval at every stage. It **self-injects** the fault
(symptom goes live), **clears it at the mitigate step**, and **waits for real recovery**
before "Resolved". It does NOT auto-exit — the final frame stays until you press **[q]**, so
you can screen-capture the complete end state. No tmux, no second terminal.

**To SEE a p95 recovery curve, use a LEAF service** (low ~24ms baseline) with `cpu_throttle` —
deep-fan-out services (billing/playback) have a huge flat baseline p95 that swamps the fault:
```bash
cd ~/Documents/maven/projects/nexusgraph-ai
INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 \
ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 \
ALERTMANAGER_URL=http://localhost:9093 KUBE_CONTEXT=kind-streamflix \
.venv/bin/python -m src.incident.demo_dashboard --service identity-service --failure-mode cpu_throttle
#   p95 climbs 0.02s → ~0.8s during the incident, then drops back to 0.02s after mitigation.
#   good leaf services: identity-service, config-service, metadata-service, account-service.
```
HITL: on a TTY you press **[a]** to approve each status update. Add `--auto-approve` for a
hands-free take. Tighten pacing with `--delay-max 2`.

**For the OOM / billing story**, recovery is pod-based (OOMKilled → Running), not p95:
```bash
… .venv/bin/python -m src.incident.demo_dashboard --service billing-service --failure-mode oom_kill
```

### Show the AGENT's work (plain, non-dashboard alternative)
A pod restart is just Kubernetes self-healing. The AI agent's value is the incident
*response* — print its full step-by-step trace (declare→triage→diagnose→mitigate→resolve→
postmortem, ~23 steps incl. root-cause hypothesis, runbook, mitigation plan, Jira):
```bash
cd ~/Documents/maven/projects/nexusgraph-ai
INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 \
ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 \
ALERTMANAGER_URL=http://localhost:9093 KUBE_CONTEXT=kind-streamflix \
.venv/bin/python -m src.incident.print_trace --service billing-service --failure-mode oom_kill --demo
```
For a richer **visual** node-by-node trace (every agent, tool call, retry, token, latency),
set `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` and run via `evaluation/incident/run_langsmith.py`
— then open the run in the LangSmith UI.

### Optional "real cluster" flourish (for the camera)
Inject a genuine fault and show it in Grafana / as a real K8s event (timing ~1 min):
```bash
cd ~/Documents/maven/projects/nexusgraph-ai/platform
make fault SVC=billing MODE=oom_kill TTL=300        # real OOMKilled
#   faster VISIBLE Grafana latency spike instead: make fault SVC=playback MODE=cpu_throttle VALUE=3
kubectl --context kind-streamflix -n streamflix-prod get pods -l app=billing-service   # see RESTARTS climb
#   Grafana Explore → rate(http_requests_total[1m])
```
The alert-driven watcher (`process_once()`) only finds an incident AFTER the alert fires
(~1-2 min). For the recording, prefer the manual run above — it's instant and deterministic.

## 4. Reset between runs
```bash
cd platform && make fault SVC=billing MODE=clear ; make fault SVC=playback MODE=clear
```

## Cold-start (only if the cluster is gone, e.g. after a reboot)
```bash
cd projects/nexusgraph-ai/platform
make up && make observe && make build deploy   # cluster + observability + 35 services
make alerts && make incident-services            # alerting + mocks
make backstage                                   # software catalog
```
This takes several minutes (Helm installs + image builds). Not needed for normal practice.

## Confidence tips
- Path A is deterministic and always looks clean — lean on it for the recorded opener.
- For Path B, the OOM/alert can take ~1 min; pre-run once before recording, or narrate the wait.
- The catalog shot is instant: `curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=component' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),"components")'`
  (Backstage port-forward: `make backstage-up`.)
