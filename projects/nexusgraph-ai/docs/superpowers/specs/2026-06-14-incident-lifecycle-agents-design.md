# Incident Lifecycle Agents — Design Spec

Date: 2026-06-14
Status: Approved
Branch: `feat/incident-lifecycle-agents`

## Summary

Add a hierarchical, multi-agent **incident-response simulation** to nexusgraph-ai.
A supervisor (Incident Commander) graph drives an incident through six lifecycle
phases, each implemented as its own LangGraph subgraph containing role-specialized
agents. The system is **primarily a teaching/portfolio simulation** (scripted
scenarios) that doubles as a **decision-support copilot** (free-text operator
input). It is **human-in-the-loop**, **read-only against the knowledge graph**, and
surfaced as a new "Incident Response" Streamlit tab whose centerpiece is a
**simulated Slack incident channel**.

This work **extends the existing repo** — it reuses the current LangChain/LangGraph
plumbing, the Neo4j-native→CSV fallback, the vector store, the trace/token
telemetry, and the Streamlit app — rather than introducing a parallel stack.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Purpose | Both: simulation engine + copilot (same agent graph, two entry modes) |
| Autonomy | Human-in-the-loop (approval gates between high-impact phases) |
| Event source | Knowledge graph + scripted scenarios (no new telemetry infra) |
| Surface | New Streamlit tab in the existing app |
| Orchestration topology | **Hierarchical** — supervisor over phase-subgraphs |
| Slack playback | Timed streaming playback |
| Slack search | Filter across message text, author, and phase |
| Slack logo | Real Slack logo (branded as a simulation) |

## Orchestration topology (hierarchical)

**Top level — Incident Commander (IC) supervisor graph.** Owns the shared
`IncidentState`, decides the next phase, enforces human-approval gates, and merges
each phase's output into one incident timeline. It only routes; it does no domain
work itself.

**Each lifecycle phase is its own compiled LangGraph subgraph**, plugged into the
supervisor as a node:

| Phase subgraph | Internal specialist agents | Grounding (read-only) |
|---|---|---|
| Declare | Intake, Severity Classifier | scenario YAML / operator text |
| Triage | Ownership, On-call, Impact/Blast-radius | `services`, `teams`, `people`, `oncall_schedules`, dependency edges |
| Diagnose | Runbook-Matcher, RCA/Dependency-traversal, Evidence (vector RAG) | `runbooks`, dep graph, Chroma docs |
| Mitigate | Mitigation-Planner, Escalation | `runbooks`, `escalation_policies` |
| Resolve | SLO-Verification, Closeout | `slo_metrics` |
| Postmortem | Scribe, Action-Item | full timeline + `audits` |

**Cross-cutting Comms agent (central).** Every subgraph emits structured timeline
events; the Comms agent renders them as messages in the simulated Slack channel,
authored by the relevant actor (Incident Bot, IC, paged on-call from
`oncall_schedules`/`people`, service owners from `teams`). "Security" is handled as
an escalation/severity branch, not a separate phase.

## Shared state & data flow

`IncidentState` (TypedDict, in the style of `hybrid_rag.State`):

- `incident`: id, title, severity, affected services
- `phase`: current lifecycle phase
- `timeline`: append-only list of events (source of truth)
- `slack_messages`: derived view — author, role, text, ts, phase
- `findings`: owners, on-call, runbook, RCA, mitigation, escalation
- `approvals`: per-gate human decisions
- `trace`: reuses `make_trace_stage()` from `hybrid_rag.py`
- `token_usage`: reuses existing accounting

**Subgraph composition:** each phase is a compiled graph added as a supervisor
node; it reads shared state, runs its internal agents, and returns a **partial
update** merged via reducers (`operator.add` for `timeline` / `slack_messages` /
`context`, mirroring the existing `context` reducer).

**Grounding:** all reads go through the existing Neo4j-native→CSV fallback and
`query_vector_store()`. The knowledge graph stays **read-only**; the incident lives
only in `IncidentState`.

## Control flow & HITL

- Supervisor routes linearly with conditional loop-backs:
  - SLO-Verification fail → return to Diagnose
  - Severity upgrade in Triage → re-run Escalation
- Human gates via LangGraph `interrupt()`:
  - Before **Mitigate** — approve the mitigation plan
  - Before **Resolve** — confirm recovery
- Approvals are recorded to the timeline and posted to Slack. Streaming playback
  advances as agents emit events; gates pause the stream until approval.

## Streamlit surface ("Incident Response" tab)

- **Left:** scenario picker (from `data/incident_scenarios.yaml`) **or** free-text
  operator input (copilot mode); Run / Approve-gate controls; reused provider
  sidebar.
- **Center:** simulated **Slack incident channel** — real Slack logo in the header,
  scrollable fixed-height feed (newest at bottom), search box filtering across
  message text / author / phase, timed streaming playback.
- **Right:** existing trace/phase view + token usage, reused from the current UI.

Slack channel naming: `#inc-<incident-slug>` (e.g. `#inc-playback-latency-sev1`).

## Reuse map (extends existing repo)

**Reused as-is:** `src/config.py` (LLM provider + Neo4j/Chroma config),
`src/vector_query.py` (`query_vector_store()`), the Neo4j-native→CSV fallback and
`graph/nodes.csv` / `graph/edges.csv`, the `data/*.yaml` knowledge graph.

**Extended:** patterns from `src/hybrid_rag.py` (`State` style, `make_trace_stage()`,
token accounting); `app/streamlit_app.py` (new tab).

**New:** `src/incident/` package, `data/incident_scenarios.yaml`,
`app/assets/slack-logo.svg`, `tests/test_incident_*.py`.

## File layout (additive)

```
src/incident/__init__.py
src/incident/state.py        # IncidentState + reducers
src/incident/agents.py       # role agents (reuse config provider plumbing)
src/incident/supervisor.py   # IC graph: routing + HITL gates
src/incident/declare.py      # phase subgraph
src/incident/triage.py       # phase subgraph
src/incident/diagnose.py     # phase subgraph
src/incident/mitigate.py     # phase subgraph
src/incident/resolve.py      # phase subgraph
src/incident/postmortem.py   # phase subgraph
src/incident/scenarios.py    # load data/incident_scenarios.yaml
src/incident/slack.py        # timeline event -> slack message model
data/incident_scenarios.yaml # scripted incidents (reference existing incident: IDs)
app/assets/slack-logo.svg
app/streamlit_app.py         # + "Incident Response" tab (edit)
tests/test_incident_*.py
```

## Testing strategy (extends existing `tests/` static-test style)

- Per-subgraph unit tests with a stubbed LLM and the CSV-fallback graph
  (deterministic): each phase produces expected findings/timeline events.
- Supervisor routing tests: linear path + each loop-back branch.
- Slack-render static tests mirroring `test_streamlit_ui_static.py`: logo present,
  scroll container, search filters by text/author/phase.
- Full scripted-scenario integration test (`playback-latency-sev1`) asserting the
  end-to-end timeline.

## Non-goals (YAGNI)

- No writes to the knowledge graph.
- No live telemetry/alerting ingestion (scripted scenarios only).
- No real Slack API integration (simulation only).
- No fully autonomous mode (human-in-the-loop only).
```
