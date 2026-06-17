# nexusgraph-ai — Week 3 Demo Walkthrough

**Target length:** 5-6 minutes
**Demo goal:** Show both selected Week 3 tracks: the incident-response agent and the project-status agent.

## Scene 1 — Title And Scope

**ON-SCREEN:** `nexusgraph-ai: Agentic operations for StreamFlix`

**VISUAL:** Streamlit app header, then the architecture diagram.

**NARRATION:**
> nexusgraph-ai started as a GraphRAG system for organizational knowledge. For Week 3, I extended it into two agentic workflows: a multi-agent IT support and incident-response simulation, and an intelligent project-status agent. Both run on the same fictional StreamFlix operations dataset.

## Scene 2 — Why A Graph

**ON-SCREEN:** `People -> teams -> services -> runbooks -> dashboards -> incidents`

**VISUAL:** Graph preview and one GraphRAG query card.

**NARRATION:**
> Operations work depends on relationships. When playback fails, the useful answer is not just a paragraph from a document. We need the owning team, current on-call engineer, runbook, dashboards, SLOs, escalation policy, dependencies, and recent incidents. Neo4j holds that connected model, while ChromaDB provides a vector baseline for comparison.

## Scene 3 — Incident Simulation Setup

**ON-SCREEN:** `Freshworks lifecycle: identify, log, prioritize, escalate, diagnose, recover, close, review`

**VISUAL:** Open the Incident Response Simulation expander.

**NARRATION:**
> The incident simulation follows a production incident lifecycle based on common ITSM practice: identify the incident, log and categorize it, prioritize severity, escalate to the right team, diagnose root cause, recover the service, close the incident, and generate a post-incident review.

## Scene 4 — Kubernetes Failure Injection

**ON-SCREEN:** `Failure modes: OOM Kill · Pod Restart · Disk IOPS · CPU Throttle`

**VISUAL:** Enable Kubernetes failure simulation and choose `oom_kill`.

**NARRATION:**
> The demo does not touch a real cluster. Instead, it loads Kubernetes resource state as key-value data and applies deterministic failure modes. When I enable simulation, the service can hit an OOM kill, repeated pod restart, disk IOPS saturation, or CPU throttling. The agents receive the affected deployment, namespace, limits, requests, restart counts, events, and degraded metrics.

## Scene 5 — Incident Agents In Action

**ON-SCREEN:** `Triage -> Diagnose -> Mitigate -> Resolve -> Postmortem`

**VISUAL:** Run the incident and show the Slack-style channel.

**NARRATION:**
> The incident commander declares the incident. The triage agent resolves ownership and on-call context from the graph. The diagnosis agent attaches Kubernetes evidence, static logs, and observability signals. The mitigation agent recommends a failure-specific plan. The resolver verifies recovery, and the postmortem agent writes the summary and action items.

## Scene 6 — Automation, Logs, And Observability

**ON-SCREEN:** `FireHydrant-style automation + OpenSearch logs + Grafana Cloud observability`

**VISUAL:** Expand Runbook automation, Static production logs, and Observability evidence.

**NARRATION:**
> The automation panel simulates FireHydrant-style runbooks: create the incident channel, open the tracking ticket, assign roles, publish a status update, capture timeline milestones, and prepare the retrospective. Static logs are captured locally for the demo, while the recommended external logging path is OpenSearch with Fluent Bit. For observability, the recommended stack is Grafana Cloud with Prometheus, Loki, Tempo, and Alertmanager.

## Scene 7 — Status Page

**ON-SCREEN:** `Streamflix Status`

**VISUAL:** Open the Streamflix Status expander.

**NARRATION:**
> The Streamflix status page is a synthetic version of a public SaaS status page. It shows component health, active customer-facing incidents, uptime summaries, and incident history so the response workflow has a customer-communication surface.

## Scene 8 — Project Status Agent

**ON-SCREEN:** `Weekly report: status, risks, blockers, dependencies, actions`

**VISUAL:** Open Project Status Agent, choose a project, generate the weekly report.

**NARRATION:**
> The second Week 3 project is the intelligent project-status agent. It reads synthetic Jira, GitHub, milestone, dependency, blocker, risk, and decision snapshots. It generates an executive summary, a red-yellow-green status, week-over-week insights, current risks, blockers, dependencies, and next actions.

## Scene 9 — Closing

**ON-SCREEN:** `Grounded agents over operational knowledge`

**VISUAL:** Return to the app overview.

**NARRATION:**
> The important part is that both workflows are grounded in the same operational knowledge base. The incident agents operate over services, runbooks, logs, observability, and status history. The project-status agent operates over delivery snapshots. Together, they show how agentic systems can support both production operations and engineering execution.

## Demo Checklist

1. Start the Streamlit app.
2. Ask a GraphRAG question: `Who is oncall for playback-service?`
3. Open `Incident Response Simulation`.
4. Enable Kubernetes failure simulation.
5. Select `oom_kill`, `pod_restart`, `disk_iops`, or `cpu_throttle`.
6. Run the incident workflow.
7. Expand runbook automation, static logs, and observability evidence.
8. Open `Streamflix Status` and show current incident plus history.
9. Open `Project Status Agent`.
10. Generate a weekly report for `Playback Resiliency 2026`.
11. Show risks, blockers, dependencies, next actions, and agent insights.
