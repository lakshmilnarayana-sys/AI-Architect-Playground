# Incident Lifecycle Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hierarchical multi-agent incident-response simulation (supervisor over six phase-subgraphs) to nexusgraph-ai, surfaced as a Streamlit section whose centerpiece is a searchable, scrolling, timed-playback simulated Slack incident channel.

**Architecture:** A LangGraph supervisor (Incident Commander) owns a shared `IncidentState` and routes through six compiled phase-subgraphs — declare → triage → diagnose → mitigate → resolve → postmortem — with conditional loop-backs and human-in-the-loop `interrupt`s before mitigate and resolve. Each phase-subgraph runs role-specialized agents that ground read-only against the existing knowledge graph (Neo4j-native → CSV fallback) and vector store. Every agent appends timeline events; the cross-cutting Comms layer renders them as Slack messages.

**Tech Stack:** Python 3.12, LangGraph 1.2.4, LangChain 1.3.4, Streamlit 1.51, pandas, PyYAML, pytest. Reuses `src/config.py`, `src/hybrid_rag.py` (`get_llm`, `query_graph_with_retry`, `make_trace_stage`), `src/vector_query.py`, `data/*.yaml`, `graph/nodes.csv`/`edges.csv`.

**Reference spec:** `docs/superpowers/specs/2026-06-14-incident-lifecycle-agents-design.md`

---

## Conventions

- All commits use the repo-local identity (lakshminarayana-sys / gmail), **no AI co-author trailer**. Signing is currently off-by-hang; commit with `git -c commit.gpgsign=false ...` until the SSH key is loaded into ssh-agent.
- Run tests from the project dir: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai`.
- All agents take an **injected `llm`** (default `None`) and an injected `GraphContext`. When `llm is None` agents fall back to deterministic templated text — this keeps every unit test LLM-free and deterministic. The LLM only rephrases Slack message prose; findings are always derived from grounding.
- Tests force the CSV fallback (no Neo4j) by constructing `GraphContext(use_neo4j=False)`, which reads `graph/nodes.csv` / `graph/edges.csv` and `data/*.yaml`.

## File Structure

| File | Responsibility |
|---|---|
| `data/incident_scenarios.yaml` | Scripted incidents (reference existing `incident:` IDs) |
| `src/incident/__init__.py` | Package marker + public exports |
| `src/incident/state.py` | `IncidentState`, `IncidentEvent`, `SlackMessage` types, reducers, `new_incident()` |
| `src/incident/scenarios.py` | Load/lookup scenarios from YAML |
| `src/incident/slack.py` | slugify, channel name, event→Slack message, role avatars, search filter |
| `src/incident/graph_lookup.py` | `GraphContext`: read-only grounding (Neo4j→CSV/YAML fallback) |
| `src/incident/agents.py` | Role agents (each returns partial state update) + `phrase()` helper |
| `src/incident/declare.py` … `postmortem.py` | One compiled phase-subgraph per file |
| `src/incident/supervisor.py` | IC graph: routing, loop-backs, HITL interrupts, `run_incident()` |
| `app/assets/slack-logo.svg` | Slack logo asset for the channel header |
| `app/streamlit_app.py` | `render_incident_response_simulation()` + wire into main script |
| `tests/test_incident_*.py` | Unit + integration tests mirroring existing static-test style |

---

## Phase 0 — Data & State Foundations

### Task 1: Scenario data + loader

**Files:**
- Create: `data/incident_scenarios.yaml`
- Create: `src/incident/__init__.py`
- Create: `src/incident/scenarios.py`
- Test: `tests/test_incident_scenarios.py`

- [ ] **Step 1: Write `data/incident_scenarios.yaml`**

```yaml
- id: "playback-latency-sev1"
  incident_id: "incident:playback-latency-sev1"
  title: "Playback Latency SEV1"
  severity: "SEV1"
  affected_services: ["Playback Service"]
  signal: "p99 playback start latency breached SLO across US-East; customers report buffering."
- id: "billing-double-charge-sev2"
  incident_id: "incident:billing-double-charge"
  title: "Billing Double Charge SEV2"
  severity: "SEV2"
  affected_services: ["Billing Service"]
  signal: "Duplicate payment captures detected in ledger reconciliation job."
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_incident_scenarios.py
from src.incident.scenarios import load_scenarios, get_scenario

def test_load_scenarios_returns_known_ids():
    scenarios = load_scenarios()
    ids = {s["id"] for s in scenarios}
    assert "playback-latency-sev1" in ids

def test_get_scenario_has_required_fields():
    s = get_scenario("playback-latency-sev1")
    assert s["severity"] == "SEV1"
    assert s["affected_services"] == ["Playback Service"]
    assert s["incident_id"].startswith("incident:")

def test_get_scenario_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_scenario("does-not-exist")
```

- [ ] **Step 3: Run it (expect fail)**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_incident_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: src.incident`

- [ ] **Step 4: Implement**

```python
# src/incident/__init__.py
"""Incident-response simulation package (hierarchical LangGraph agents)."""
```

```python
# src/incident/scenarios.py
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = ROOT / "data" / "incident_scenarios.yaml"


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def get_scenario(scenario_id: str, path: Path = SCENARIOS_PATH) -> dict:
    for scenario in load_scenarios(path):
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario: {scenario_id}")
```

- [ ] **Step 5: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_scenarios.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add data/incident_scenarios.yaml src/incident/__init__.py src/incident/scenarios.py tests/test_incident_scenarios.py
git -c commit.gpgsign=false commit -m "feat(incident): add scenario data and loader"
```

---

### Task 2: Shared state model + reducers

**Files:**
- Create: `src/incident/state.py`
- Test: `tests/test_incident_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_state.py
from src.incident.state import new_incident, merge_findings, IncidentEvent

def test_new_incident_seeds_core_fields():
    state = new_incident(
        incident_id="incident:playback-latency-sev1",
        title="Playback Latency SEV1",
        severity="SEV1",
        affected_services=["Playback Service"],
        signal="latency breach",
    )
    assert state["phase"] == "declare"
    assert state["incident"]["severity"] == "SEV1"
    assert state["timeline"] == []
    assert state["slack_messages"] == []
    assert state["findings"] == {}

def test_merge_findings_is_shallow_update():
    merged = merge_findings({"owner": "A"}, {"oncall": "B"})
    assert merged == {"owner": "A", "oncall": "B"}

def test_merge_findings_overwrites_key():
    assert merge_findings({"severity": "SEV2"}, {"severity": "SEV1"})["severity"] == "SEV1"
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_state.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/state.py
import operator
from typing import Annotated, Any, Optional, TypedDict


class IncidentEvent(TypedDict, total=False):
    ts: str          # ISO-ish "HH:MM:SS"
    phase: str
    actor: str       # display name, e.g. "TriageAgent" or "J. Okafor"
    role: str        # one of ROLE_* keys (see slack.py)
    kind: str        # "message" | "action" | "gate" | "finding"
    text: str
    details: dict


class SlackMessage(TypedDict, total=False):
    ts: str
    author: str
    role: str
    phase: str
    text: str
    avatar: str


def merge_findings(current: Optional[dict], new: Optional[dict]) -> dict:
    out = dict(current or {})
    out.update(new or {})
    return out


class IncidentState(TypedDict, total=False):
    incident: dict
    phase: str
    timeline: Annotated[list[IncidentEvent], operator.add]
    slack_messages: Annotated[list[SlackMessage], operator.add]
    findings: Annotated[dict, merge_findings]
    approvals: Annotated[dict, merge_findings]
    trace: Optional[dict]
    token_usage: dict
    route: Optional[str]   # next-phase hint set by supervisor


def new_incident(
    incident_id: str,
    title: str,
    severity: str,
    affected_services: list[str],
    signal: str,
) -> IncidentState:
    return {
        "incident": {
            "id": incident_id,
            "title": title,
            "severity": severity,
            "affected_services": list(affected_services),
            "signal": signal,
        },
        "phase": "declare",
        "timeline": [],
        "slack_messages": [],
        "findings": {},
        "approvals": {},
        "trace": None,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "route": None,
    }
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_state.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/state.py tests/test_incident_state.py
git -c commit.gpgsign=false commit -m "feat(incident): add shared IncidentState and reducers"
```

---

### Task 3: Slack message model + search

**Files:**
- Create: `src/incident/slack.py`
- Test: `tests/test_incident_slack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_slack.py
from src.incident.slack import (
    slugify, channel_name, event_to_slack_message, filter_messages, ROLE_AVATARS,
)

def test_slugify_and_channel_name():
    assert slugify("Playback Latency SEV1") == "playback-latency-sev1"
    assert channel_name({"title": "Playback Latency SEV1"}) == "#inc-playback-latency-sev1"

def test_event_to_slack_message_maps_fields_and_avatar():
    event = {"ts": "10:02:00", "phase": "declare", "actor": "Incident Bot",
             "role": "bot", "kind": "message", "text": "SEV1 declared"}
    msg = event_to_slack_message(event)
    assert msg["author"] == "Incident Bot"
    assert msg["phase"] == "declare"
    assert msg["avatar"] == ROLE_AVATARS["bot"]
    assert msg["text"] == "SEV1 declared"

def test_filter_messages_matches_text_author_and_phase():
    messages = [
        {"ts": "1", "author": "TriageAgent", "role": "triage", "phase": "triage", "text": "owner is Playback Platform", "avatar": "x"},
        {"ts": "2", "author": "Incident Bot", "role": "bot", "phase": "declare", "text": "SEV1 declared", "avatar": "y"},
    ]
    assert len(filter_messages(messages, "")) == 2          # empty = all
    assert len(filter_messages(messages, "playback")) == 1  # text
    assert len(filter_messages(messages, "bot")) == 1       # author
    assert len(filter_messages(messages, "triage")) == 1    # phase
    assert filter_messages(messages, "PLAYBACK")[0]["author"] == "TriageAgent"  # case-insensitive
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_slack.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/slack.py
import re
from src.incident.state import IncidentEvent, SlackMessage

ROLE_AVATARS = {
    "bot": "🤖",
    "commander": "🧭",
    "triage": "🔎",
    "diagnose": "🩺",
    "mitigate": "🛠️",
    "resolve": "✅",
    "postmortem": "📝",
    "oncall": "👤",
    "owner": "👥",
    "comms": "📣",
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug


def channel_name(incident: dict) -> str:
    return f"#inc-{slugify(incident.get('title', 'incident'))}"


def event_to_slack_message(event: IncidentEvent) -> SlackMessage:
    role = event.get("role", "bot")
    return {
        "ts": event.get("ts", ""),
        "author": event.get("actor", "Incident Bot"),
        "role": role,
        "phase": event.get("phase", ""),
        "text": event.get("text", ""),
        "avatar": ROLE_AVATARS.get(role, "💬"),
    }


def filter_messages(messages: list[SlackMessage], query: str) -> list[SlackMessage]:
    q = (query or "").strip().lower()
    if not q:
        return list(messages)
    return [
        m for m in messages
        if q in m.get("text", "").lower()
        or q in m.get("author", "").lower()
        or q in m.get("phase", "").lower()
        or q in m.get("role", "").lower()
    ]
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_slack.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/slack.py tests/test_incident_slack.py
git -c commit.gpgsign=false commit -m "feat(incident): add Slack message model and search filter"
```

---

### Task 4: Grounding context (Neo4j → CSV/YAML fallback)

**Files:**
- Create: `src/incident/graph_lookup.py`
- Test: `tests/test_incident_graph_lookup.py`

`GraphContext` is read-only. With `use_neo4j=True` it calls `query_graph_with_retry` from `hybrid_rag`; on any failure (or `use_neo4j=False`) it falls back to reading `data/*.yaml` and `graph/edges.csv`. Tests use `use_neo4j=False` for determinism.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_graph_lookup.py
from src.incident.graph_lookup import GraphContext

def test_runbooks_for_service_from_yaml_fallback():
    ctx = GraphContext(use_neo4j=False)
    runbooks = ctx.runbooks_for("Playback Service")
    assert any("playback" in r["id"].lower() for r in runbooks)

def test_escalation_for_severity_returns_policy():
    ctx = GraphContext(use_neo4j=False)
    policy = ctx.escalation_for("Playback Service", "SEV1")
    assert policy is not None
    assert "escalation:" in policy["id"]

def test_slo_for_service_returns_list():
    ctx = GraphContext(use_neo4j=False)
    assert isinstance(ctx.slo_for("Playback Service"), list)

def test_owner_and_oncall_never_raise():
    ctx = GraphContext(use_neo4j=False)
    # May be None when CSV lacks an edge, but must not raise.
    ctx.owner_for("Playback Service")
    ctx.oncall_for("Playback Service")
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_graph_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/graph_lookup.py
from pathlib import Path
import csv
import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
GRAPH = ROOT / "graph"


def _load_yaml(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def _keyword_match(haystack: str, needle: str) -> bool:
    h = (haystack or "").lower()
    return any(tok in h for tok in needle.lower().split())


class GraphContext:
    """Read-only grounding over the knowledge graph with CSV/YAML fallback."""

    def __init__(self, use_neo4j: bool = True):
        self.use_neo4j = use_neo4j

    # --- Neo4j attempt with safe fallback -------------------------------
    def _neo4j(self, cypher: str):
        if not self.use_neo4j:
            return None
        try:
            from src.hybrid_rag import query_graph_with_retry
            rows, _attempts, _source = query_graph_with_retry(cypher)
            return rows
        except Exception:
            return None

    # --- Public lookups -------------------------------------------------
    def runbooks_for(self, service: str) -> list[dict]:
        rows = self._neo4j(
            f"MATCH (r:Runbook) WHERE r.name =~ '(?i).*{service.split()[0]}.*' "
            f"RETURN r.id AS id, r.name AS name LIMIT 10"
        )
        if rows:
            return [{"id": r.get("id"), "name": r.get("name")} for r in rows]
        return [r for r in _load_yaml("runbooks.yaml") if _keyword_match(r.get("name", ""), service)]

    def escalation_for(self, service: str, severity: str) -> dict | None:
        policies = _load_yaml("escalation_policies.yaml")
        sev = severity.lower()
        token = service.split()[0].lower()
        for p in policies:
            blob = (p.get("name", "") + " " + p.get("description", "")).lower()
            if token in blob and (sev in blob or sev[:-1] in blob or "escalat" in blob):
                return {"id": p["id"], "name": p.get("name")}
        for p in policies:
            if token in (p.get("name", "") + p.get("description", "")).lower():
                return {"id": p["id"], "name": p.get("name")}
        return None

    def slo_for(self, service: str) -> list[dict]:
        return [s for s in _load_yaml("slo_metrics.yaml") if _keyword_match(s.get("name", ""), service)]

    def owner_for(self, service: str) -> dict | None:
        return self._edge_target(service, ("OWNS", "OWNED_BY", "OWNER"))

    def oncall_for(self, service: str) -> dict | None:
        return self._edge_target(service, ("ON_CALL", "ONCALL", "RESPONSIBLE_FOR"))

    # --- CSV edge traversal fallback ------------------------------------
    def _edge_target(self, service: str, rel_types: tuple[str, ...]) -> dict | None:
        edges_path = GRAPH / "edges.csv"
        nodes_path = GRAPH / "nodes.csv"
        if not edges_path.exists() or not nodes_path.exists():
            return None
        with open(nodes_path, newline="", encoding="utf-8") as fh:
            nodes = {row["id"]: row for row in csv.DictReader(fh)}
        token = service.split()[0].lower()
        svc_ids = {nid for nid, n in nodes.items()
                   if token in (n.get("name", "") + n.get("id", "")).lower()}
        with open(edges_path, newline="", encoding="utf-8") as fh:
            for e in csv.DictReader(fh):
                rel = (e.get("relationship", "") or "").upper()
                if any(rt in rel for rt in rel_types):
                    if e.get("source") in svc_ids and e.get("target") in nodes:
                        return {"id": e["target"], "name": nodes[e["target"]].get("name")}
                    if e.get("target") in svc_ids and e.get("source") in nodes:
                        return {"id": e["source"], "name": nodes[e["source"]].get("name")}
        return None
```

> NOTE: confirm `graph/nodes.csv` column names (`id`, `name`, `label`) and `graph/edges.csv` (`source`, `target`, `relationship`) before running; adjust keys if the headers differ. The test only asserts "never raises" for owner/oncall, so header drift won't break the suite, but fix keys so lookups actually resolve.

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_graph_lookup.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/graph_lookup.py tests/test_incident_graph_lookup.py
git -c commit.gpgsign=false commit -m "feat(incident): add read-only GraphContext grounding with CSV fallback"
```

---

## Phase 1 — Agents & Phase Subgraphs

### Task 5: Agent helpers + deterministic phrasing

**Files:**
- Create: `src/incident/agents.py`
- Test: `tests/test_incident_agents.py`

`emit()` builds a timeline event AND its Slack message in one call so every agent stays one-liner consistent. `phrase()` uses the injected LLM when present, else returns the deterministic fallback string.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_agents.py
from src.incident.agents import emit, phrase

class FakeLLM:
    def invoke(self, prompt):
        class R: content = "LLM-PHRASED"
        return R()

def test_emit_produces_event_and_slack_update():
    update = emit(phase="declare", actor="Incident Bot", role="bot",
                  kind="message", text="SEV1 declared", ts="10:00:00")
    assert update["timeline"][0]["text"] == "SEV1 declared"
    assert update["slack_messages"][0]["author"] == "Incident Bot"
    assert update["slack_messages"][0]["avatar"]  # avatar resolved

def test_phrase_uses_fallback_without_llm():
    assert phrase(None, "ignored", fallback="FB") == "FB"

def test_phrase_uses_llm_when_present():
    assert phrase(FakeLLM(), "prompt", fallback="FB") == "LLM-PHRASED"
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_agents.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/agents.py
from src.incident.slack import event_to_slack_message


def emit(phase: str, actor: str, role: str, kind: str, text: str,
         ts: str = "", details: dict | None = None) -> dict:
    """Return a partial IncidentState update carrying one event + its Slack message."""
    event = {
        "ts": ts, "phase": phase, "actor": actor, "role": role,
        "kind": kind, "text": text, "details": details or {},
    }
    return {"timeline": [event], "slack_messages": [event_to_slack_message(event)]}


def phrase(llm, prompt: str, fallback: str) -> str:
    """Use the LLM to phrase a message when available; else deterministic fallback."""
    if llm is None:
        return fallback
    try:
        return llm.invoke(prompt).content.strip() or fallback
    except Exception:
        return fallback
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_agents.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/agents.py tests/test_incident_agents.py
git -c commit.gpgsign=false commit -m "feat(incident): add agent emit/phrase helpers"
```

---

### Task 6: Declare phase-subgraph

**Files:**
- Create: `src/incident/declare.py`
- Test: `tests/test_incident_declare.py`

Internal agents: **Intake** (announces the incident + signal), **Severity Classifier** (records severity finding). Returns a compiled LangGraph subgraph sharing `IncidentState`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_declare.py
from src.incident.declare import build_declare_subgraph
from src.incident.state import new_incident

def test_declare_subgraph_emits_intake_and_severity():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    out = build_declare_subgraph(llm=None).invoke(state)
    texts = " ".join(e["text"] for e in out["timeline"])
    assert "SEV1" in texts
    assert out["findings"]["severity"] == "SEV1"
    assert out["phase"] == "declare"
    roles = {m["role"] for m in out["slack_messages"]}
    assert "bot" in roles
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_declare.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/declare.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.agents import emit, phrase


def _intake(state: IncidentState, llm=None) -> dict:
    inc = state["incident"]
    text = phrase(
        llm,
        f"Announce incident declaration for {inc['title']} given signal: {inc['signal']}",
        fallback=f"{inc['severity']} declared · {inc['title']} — {inc['signal']}",
    )
    return {"phase": "declare", **emit("declare", "Incident Bot", "bot", "message", text)}


def _severity(state: IncidentState, llm=None) -> dict:
    sev = state["incident"]["severity"]
    update = emit("declare", "Severity Classifier", "commander", "finding",
                  f"Severity confirmed: {sev}")
    update["findings"] = {"severity": sev}
    return update


def build_declare_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("intake", partial(_intake, llm=llm))
    g.add_node("severity", partial(_severity, llm=llm))
    g.add_edge(START, "intake")
    g.add_edge("intake", "severity")
    g.add_edge("severity", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_declare.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/declare.py tests/test_incident_declare.py
git -c commit.gpgsign=false commit -m "feat(incident): add declare phase subgraph"
```

---

### Task 7: Triage phase-subgraph

**Files:**
- Create: `src/incident/triage.py`
- Test: `tests/test_incident_triage.py`

Internal agents: **Ownership** (owner_for), **On-call** (oncall_for), **Impact** (affected services / blast radius). All ground via `GraphContext`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_triage.py
from src.incident.triage import build_triage_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

def test_triage_records_findings_and_messages():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    out = build_triage_subgraph(llm=None, ctx=GraphContext(use_neo4j=False)).invoke(state)
    assert "impact" in out["findings"]
    assert "Playback Service" in out["findings"]["impact"]
    # owner/oncall keys always present (value may be None on CSV gaps)
    assert "owner" in out["findings"] and "oncall" in out["findings"]
    assert any(m["role"] == "triage" for m in out["slack_messages"])
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_triage.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/triage.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit


def _primary_service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _ownership(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _primary_service(state)
    owner = ctx.owner_for(svc)
    name = owner["name"] if owner else "unmapped owner"
    update = emit("triage", "TriageAgent", "triage", "finding", f"Owner of {svc}: {name}")
    update["findings"] = {"owner": owner}
    return update


def _oncall(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _primary_service(state)
    oncall = ctx.oncall_for(svc)
    name = oncall["name"] if oncall else "no on-call mapped"
    update = emit("triage", "TriageAgent", "oncall", "action", f"Paging on-call for {svc}: {name}")
    update["findings"] = {"oncall": oncall}
    return update


def _impact(state: IncidentState, ctx: GraphContext) -> dict:
    services = state["incident"].get("affected_services") or []
    blast = ", ".join(services) or "scope under assessment"
    update = emit("triage", "TriageAgent", "triage", "finding", f"Impact / blast radius: {blast}")
    update["findings"] = {"impact": services}
    return update


def build_triage_subgraph(llm=None, ctx: GraphContext | None = None):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("ownership", partial(_ownership, ctx=ctx))
    g.add_node("oncall", partial(_oncall, ctx=ctx))
    g.add_node("impact", partial(_impact, ctx=ctx))
    g.add_edge(START, "ownership")
    g.add_edge("ownership", "oncall")
    g.add_edge("oncall", "impact")
    g.add_edge("impact", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_triage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/triage.py tests/test_incident_triage.py
git -c commit.gpgsign=false commit -m "feat(incident): add triage phase subgraph"
```

---

### Task 8: Diagnose phase-subgraph

**Files:**
- Create: `src/incident/diagnose.py`
- Test: `tests/test_incident_diagnose.py`

Internal agents: **Runbook-Matcher** (runbooks_for), **RCA** (heuristic hypothesis from signal), **Evidence** (vector RAG; wrapped so failure degrades gracefully).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_diagnose.py
from src.incident.diagnose import build_diagnose_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

def test_diagnose_matches_runbook_and_sets_rca():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "p99 latency breach on CDN")
    out = build_diagnose_subgraph(llm=None, ctx=GraphContext(use_neo4j=False),
                                  use_vector=False).invoke(state)
    assert out["findings"]["runbook"] is not None
    assert "playback" in out["findings"]["runbook"]["id"].lower()
    assert out["findings"]["rca"]            # non-empty hypothesis
    assert any(m["role"] == "diagnose" for m in out["slack_messages"])
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_diagnose.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/diagnose.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit, phrase


def _service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _runbook(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _service(state)
    matches = ctx.runbooks_for(svc)
    chosen = matches[0] if matches else None
    name = chosen["name"] if chosen else "no matching runbook"
    update = emit("diagnose", "DiagnoseAgent", "diagnose", "finding", f"Runbook matched: {name}")
    update["findings"] = {"runbook": chosen}
    return update


def _rca(state: IncidentState, llm=None) -> dict:
    signal = state["incident"].get("signal", "")
    svc = _service(state)
    hypothesis = phrase(
        llm,
        f"Give a one-line root-cause hypothesis for {svc} given: {signal}",
        fallback=f"Leading hypothesis: degradation in {svc} consistent with '{signal}'.",
    )
    update = emit("diagnose", "DiagnoseAgent", "diagnose", "finding", hypothesis)
    update["findings"] = {"rca": hypothesis}
    return update


def _evidence(state: IncidentState, use_vector: bool) -> dict:
    snippet = "Vector evidence skipped"
    if use_vector:
        try:
            from src.vector_query import query_vector_store
            res = query_vector_store(state["incident"].get("signal", ""))
            matches = res.get("matches", [])
            snippet = f"Retrieved {len(matches)} supporting document(s)."
        except Exception as exc:
            snippet = f"Vector evidence unavailable ({type(exc).__name__})."
    return emit("diagnose", "EvidenceAgent", "diagnose", "action", snippet)


def build_diagnose_subgraph(llm=None, ctx: GraphContext | None = None, use_vector: bool = True):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("runbook", partial(_runbook, ctx=ctx))
    g.add_node("rca", partial(_rca, llm=llm))
    g.add_node("evidence", partial(_evidence, use_vector=use_vector))
    g.add_edge(START, "runbook")
    g.add_edge("runbook", "rca")
    g.add_edge("rca", "evidence")
    g.add_edge("evidence", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_diagnose.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/diagnose.py tests/test_incident_diagnose.py
git -c commit.gpgsign=false commit -m "feat(incident): add diagnose phase subgraph"
```

---

### Task 9: Mitigate phase-subgraph

**Files:**
- Create: `src/incident/mitigate.py`
- Test: `tests/test_incident_mitigate.py`

Internal agents: **Mitigation-Planner** (proposes steps from matched runbook), **Escalation** (escalation_for by severity).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_mitigate.py
from src.incident.mitigate import build_mitigate_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

def test_mitigate_sets_plan_and_escalation():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["findings"] = {"runbook": {"id": "runbook:playback-latency", "name": "Playback Latency Runbook"}}
    out = build_mitigate_subgraph(llm=None, ctx=GraphContext(use_neo4j=False)).invoke(state)
    assert out["findings"]["mitigation_plan"]
    assert out["findings"]["escalation"] is not None
    assert any(m["role"] == "mitigate" for m in out["slack_messages"])
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_mitigate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/mitigate.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit, phrase


def _service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _planner(state: IncidentState, llm=None) -> dict:
    runbook = (state.get("findings") or {}).get("runbook")
    rb_name = runbook["name"] if runbook else "standard mitigation steps"
    plan = phrase(
        llm,
        f"Propose a concise mitigation plan for {_service(state)} following {rb_name}.",
        fallback=f"Proposed mitigation per {rb_name}: stabilize, fail over, verify recovery.",
    )
    update = emit("mitigate", "MitigationPlanner", "mitigate", "action", plan)
    update["findings"] = {"mitigation_plan": plan}
    return update


def _escalation(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _service(state)
    sev = state["incident"].get("severity", "SEV3")
    policy = ctx.escalation_for(svc, sev)
    name = policy["name"] if policy else "no escalation policy mapped"
    update = emit("mitigate", "EscalationAgent", "mitigate", "action", f"Escalation policy: {name}")
    update["findings"] = {"escalation": policy}
    return update


def build_mitigate_subgraph(llm=None, ctx: GraphContext | None = None):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("planner", partial(_planner, llm=llm))
    g.add_node("escalation", partial(_escalation, ctx=ctx))
    g.add_edge(START, "planner")
    g.add_edge("planner", "escalation")
    g.add_edge("escalation", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_mitigate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/mitigate.py tests/test_incident_mitigate.py
git -c commit.gpgsign=false commit -m "feat(incident): add mitigate phase subgraph"
```

---

### Task 10: Resolve phase-subgraph (with SLO-verification outcome)

**Files:**
- Create: `src/incident/resolve.py`
- Test: `tests/test_incident_resolve.py`

Internal agents: **SLO-Verification** (sets `findings["slo_recovered"]` bool — drives supervisor loop-back), **Closeout**. The simulation reads recovery from the scenario (`recovered` defaults True); copilot mode defaults True. A scenario can set `recovered: false` to exercise the loop-back to Diagnose.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_resolve.py
from src.incident.resolve import build_resolve_subgraph
from src.incident.state import new_incident

def _state(recovered=True):
    s = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                     "SEV1", ["Playback Service"], "latency breach")
    s["incident"]["recovered"] = recovered
    return s

def test_resolve_marks_recovered_true():
    out = build_resolve_subgraph(llm=None).invoke(_state(True))
    assert out["findings"]["slo_recovered"] is True

def test_resolve_marks_recovered_false():
    out = build_resolve_subgraph(llm=None).invoke(_state(False))
    assert out["findings"]["slo_recovered"] is False
    assert any("not recovered" in m["text"].lower() for m in out["slack_messages"])
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/resolve.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.agents import emit


def _verify(state: IncidentState) -> dict:
    recovered = bool(state["incident"].get("recovered", True))
    svc = (state["incident"].get("affected_services") or ["service"])[0]
    text = (f"SLO verification: {svc} recovered within target."
            if recovered else
            f"SLO verification: {svc} has NOT recovered — recommend re-diagnose.")
    update = emit("resolve", "SLOVerification", "resolve", "finding", text)
    update["findings"] = {"slo_recovered": recovered}
    return update


def _closeout(state: IncidentState) -> dict:
    if not state["incident"].get("recovered", True):
        return emit("resolve", "Incident Commander", "commander", "message",
                    "Holding resolution — looping back to diagnosis.")
    return emit("resolve", "Incident Commander", "commander", "message",
                "Incident mitigated and verified; moving to postmortem.")


def build_resolve_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("verify", _verify)
    g.add_node("closeout", _closeout)
    g.add_edge(START, "verify")
    g.add_edge("verify", "closeout")
    g.add_edge("closeout", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_resolve.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/resolve.py tests/test_incident_resolve.py
git -c commit.gpgsign=false commit -m "feat(incident): add resolve phase subgraph with SLO verification"
```

---

### Task 11: Postmortem phase-subgraph

**Files:**
- Create: `src/incident/postmortem.py`
- Test: `tests/test_incident_postmortem.py`

Internal agents: **Scribe** (renders the timeline into a markdown postmortem stored in `findings["postmortem_md"]`), **Action-Item** (derives follow-ups).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_postmortem.py
from src.incident.postmortem import build_postmortem_subgraph
from src.incident.state import new_incident

def test_postmortem_emits_markdown_and_actions():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["timeline"] = [{"ts": "10:00:00", "phase": "declare", "actor": "Incident Bot",
                          "role": "bot", "kind": "message", "text": "SEV1 declared", "details": {}}]
    out = build_postmortem_subgraph(llm=None).invoke(state)
    md = out["findings"]["postmortem_md"]
    assert "# Postmortem" in md
    assert "Playback Latency SEV1" in md
    assert out["findings"]["action_items"]
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_postmortem.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/postmortem.py
from langgraph.graph import StateGraph, START, END
from src.incident.state import IncidentState
from src.incident.agents import emit


def _scribe(state: IncidentState) -> dict:
    inc = state["incident"]
    lines = [f"# Postmortem — {inc['title']}", "",
             f"- Severity: {inc['severity']}",
             f"- Affected: {', '.join(inc.get('affected_services', []))}",
             f"- Signal: {inc.get('signal', '')}", "", "## Timeline", ""]
    for e in state.get("timeline", []):
        lines.append(f"- `{e.get('ts','')}` **{e.get('actor','')}** ({e.get('phase','')}): {e.get('text','')}")
    md = "\n".join(lines)
    update = emit("postmortem", "Scribe", "postmortem", "action", "Postmortem drafted from timeline.")
    update["findings"] = {"postmortem_md": md}
    return update


def _action_items(state: IncidentState) -> dict:
    items = [
        "Add/verify alerting threshold for the affected SLO.",
        "Review runbook accuracy against this incident.",
        "Confirm on-call coverage and escalation path.",
    ]
    update = emit("postmortem", "ActionItemAgent", "postmortem", "finding",
                  f"{len(items)} follow-up action item(s) created.")
    update["findings"] = {"action_items": items}
    return update


def build_postmortem_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("scribe", _scribe)
    g.add_node("actions", _action_items)
    g.add_edge(START, "scribe")
    g.add_edge("scribe", "actions")
    g.add_edge("actions", END)
    return g.compile()
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_postmortem.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/postmortem.py tests/test_incident_postmortem.py
git -c commit.gpgsign=false commit -m "feat(incident): add postmortem phase subgraph"
```

---

## Phase 2 — Supervisor Orchestration

### Task 12: Incident Commander supervisor (routing + loop-back + HITL)

**Files:**
- Create: `src/incident/supervisor.py`
- Test: `tests/test_incident_supervisor.py`

The supervisor wires the six compiled subgraphs as nodes. A `_set_phase_*` shim before each subgraph stamps `state["phase"]`. Routing is linear except after `resolve`: if `findings["slo_recovered"]` is False → back to `diagnose`, else → `postmortem`. HITL via `interrupt_before=["mitigate", "resolve"]` with a `MemorySaver` checkpointer.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_supervisor.py
from src.incident.supervisor import build_incident_graph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

CTX = GraphContext(use_neo4j=False)

def _run_to_completion(state, config):
    graph = build_incident_graph(llm=None, ctx=CTX, use_vector=False)
    graph.invoke(state, config=config)
    # auto-approve both HITL gates
    while graph.get_state(config).next:
        graph.invoke(None, config=config)
    return graph.get_state(config).values

def test_happy_path_reaches_postmortem():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    cfg = {"configurable": {"thread_id": "t1"}}
    values = _run_to_completion(state, cfg)
    assert values["findings"]["postmortem_md"]
    phases = [e["phase"] for e in values["timeline"]]
    assert "postmortem" in phases

def test_failed_slo_loops_back_to_diagnose():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = False  # never recovers -> loop guard caps re-diagnose
    cfg = {"configurable": {"thread_id": "t2"}}
    values = _run_to_completion(state, cfg)
    diagnose_runs = sum(1 for e in values["timeline"]
                        if e["phase"] == "diagnose" and e["actor"] == "EvidenceAgent")
    assert diagnose_runs >= 2  # initial + at least one loop-back

def test_hitl_interrupts_before_mitigate():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    cfg = {"configurable": {"thread_id": "t3"}}
    graph = build_incident_graph(llm=None, ctx=CTX, use_vector=False)
    graph.invoke(state, config=cfg)
    assert graph.get_state(cfg).next  # paused at an interrupt before mitigate
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_supervisor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/incident/supervisor.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.declare import build_declare_subgraph
from src.incident.triage import build_triage_subgraph
from src.incident.diagnose import build_diagnose_subgraph
from src.incident.mitigate import build_mitigate_subgraph
from src.incident.resolve import build_resolve_subgraph
from src.incident.postmortem import build_postmortem_subgraph

MAX_REDIAGNOSE = 2  # loop-back guard so a never-recovering scenario still terminates


def _phase_setter(name: str):
    def _set(state: IncidentState) -> dict:
        return {"phase": name}
    return _set


def _route_after_resolve(state: IncidentState) -> str:
    findings = state.get("findings") or {}
    attempts = (state.get("incident") or {}).get("_diagnose_attempts", 0)
    if not findings.get("slo_recovered", True) and attempts < MAX_REDIAGNOSE:
        return "rediagnose"
    return "postmortem"


def _bump_attempts(state: IncidentState) -> dict:
    inc = dict(state.get("incident") or {})
    inc["_diagnose_attempts"] = inc.get("_diagnose_attempts", 0) + 1
    return {"incident": inc}


def build_incident_graph(llm=None, ctx: GraphContext | None = None, use_vector: bool = True):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)

    g.add_node("declare", build_declare_subgraph(llm=llm))
    g.add_node("triage", build_triage_subgraph(llm=llm, ctx=ctx))
    g.add_node("set_diagnose", _phase_setter("diagnose"))
    g.add_node("diagnose", build_diagnose_subgraph(llm=llm, ctx=ctx, use_vector=use_vector))
    g.add_node("bump", _bump_attempts)
    g.add_node("set_mitigate", _phase_setter("mitigate"))
    g.add_node("mitigate", build_mitigate_subgraph(llm=llm, ctx=ctx))
    g.add_node("set_resolve", _phase_setter("resolve"))
    g.add_node("resolve", build_resolve_subgraph(llm=llm))
    g.add_node("postmortem", build_postmortem_subgraph(llm=llm))

    g.add_edge(START, "declare")
    g.add_edge("declare", "triage")
    g.add_edge("triage", "set_diagnose")
    g.add_edge("set_diagnose", "diagnose")
    g.add_edge("diagnose", "bump")
    g.add_edge("bump", "set_mitigate")
    g.add_edge("set_mitigate", "mitigate")
    g.add_edge("mitigate", "set_resolve")
    g.add_edge("set_resolve", "resolve")
    g.add_conditional_edges("resolve", _route_after_resolve,
                            {"rediagnose": "set_diagnose", "postmortem": "postmortem"})
    g.add_edge("postmortem", END)

    return g.compile(checkpointer=MemorySaver(),
                     interrupt_before=["set_mitigate", "set_resolve"])


def run_incident(state: IncidentState, llm=None, ctx: GraphContext | None = None,
                 use_vector: bool = True, thread_id: str = "incident"):
    """Convenience: run to completion, auto-approving HITL gates. Returns final state."""
    graph = build_incident_graph(llm=llm, ctx=ctx, use_vector=use_vector)
    cfg = {"configurable": {"thread_id": thread_id}}
    graph.invoke(state, config=cfg)
    while graph.get_state(cfg).next:
        graph.invoke(None, config=cfg)
    return graph.get_state(cfg).values
```

> NOTE: The HITL interrupt is placed on the `set_mitigate`/`set_resolve` shim nodes so the pause happens *before* the corresponding subgraph runs. The `bump` node increments a hidden `_diagnose_attempts` counter on each diagnose pass; `MAX_REDIAGNOSE` guarantees termination even when `recovered` stays False.

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_supervisor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/supervisor.py tests/test_incident_supervisor.py
git -c commit.gpgsign=false commit -m "feat(incident): add IC supervisor with routing, loop-back, and HITL gates"
```

---

### Task 13: Streaming driver for the UI

**Files:**
- Modify: `src/incident/supervisor.py` (add `stream_incident`)
- Test: `tests/test_incident_stream.py`

`stream_incident` yields `(phase, new_slack_messages)` deltas as the graph advances, pausing at gates and resuming when an `approve` callback returns True — this powers the timed Slack playback.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_incident_stream.py
from src.incident.supervisor import stream_incident
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

def test_stream_yields_messages_and_completes():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    seen = []
    for phase, messages in stream_incident(state, llm=None,
                                           ctx=GraphContext(use_neo4j=False),
                                           use_vector=False, approve=lambda phase: True,
                                           thread_id="s1"):
        seen.extend(messages)
    assert any(m["role"] == "postmortem" for m in seen)
    assert any(m["role"] == "bot" for m in seen)
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_stream.py -v`
Expected: FAIL — `ImportError: cannot import name 'stream_incident'`

- [ ] **Step 3: Implement (append to `src/incident/supervisor.py`)**

```python
def stream_incident(state, llm=None, ctx=None, use_vector=True,
                    approve=None, thread_id="incident"):
    """Yield (phase, new_messages) as the incident advances.

    `approve(phase)` is called at each HITL gate; returning False aborts the run.
    """
    approve = approve or (lambda phase: True)
    graph = build_incident_graph(llm=llm, ctx=ctx, use_vector=use_vector)
    cfg = {"configurable": {"thread_id": thread_id}}
    emitted = 0

    def _drain():
        nonlocal emitted
        values = graph.get_state(cfg).values
        msgs = values.get("slack_messages", [])
        new = msgs[emitted:]
        emitted = len(msgs)
        return values.get("phase", ""), new

    graph.invoke(state, config=cfg)
    phase, new = _drain()
    if new:
        yield phase, new

    while graph.get_state(cfg).next:
        pending_phase = graph.get_state(cfg).values.get("phase", "")
        if not approve(pending_phase):
            return
        graph.invoke(None, config=cfg)
        phase, new = _drain()
        if new:
            yield phase, new
```

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_stream.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add src/incident/supervisor.py tests/test_incident_stream.py
git -c commit.gpgsign=false commit -m "feat(incident): add streaming driver for Slack playback"
```

---

## Phase 3 — Streamlit Surface

### Task 14: Slack logo asset + channel render helper

**Files:**
- Create: `app/assets/slack-logo.svg`
- Modify: `app/streamlit_app.py` (add `render_slack_channel`)
- Test: `tests/test_incident_ui_static.py`

Static tests follow the existing `tests/test_streamlit_ui_static.py` pattern: read the source and assert structure/strings (no Streamlit runtime).

- [ ] **Step 1: Add the Slack logo asset**

Download the official multicolor Slack logo SVG into `app/assets/slack-logo.svg`. Verify it is valid SVG:

```bash
mkdir -p app/assets
curl -fsSL "https://upload.wikimedia.org/wikipedia/commons/d/d5/Slack_icon_2019.svg" -o app/assets/slack-logo.svg
head -c 200 app/assets/slack-logo.svg   # expect "<svg" near the start
```

If the download is unavailable, hand-create a minimal valid `<svg>…</svg>` with the four Slack-color rounded shapes; the test only requires the file to exist and contain `<svg`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_incident_ui_static.py
from pathlib import Path

APP = Path("app/streamlit_app.py").read_text()

def test_slack_logo_asset_exists_and_is_svg():
    svg = Path("app/assets/slack-logo.svg")
    assert svg.exists()
    assert "<svg" in svg.read_text()[:300]

def test_render_slack_channel_defined():
    assert "def render_slack_channel(" in APP

def test_slack_channel_has_search_and_scroll():
    assert "filter_messages(" in APP        # search wired in
    assert "st.text_input" in APP and "Search messages" in APP
    assert "height=" in APP                  # scrollable fixed-height container
```

- [ ] **Step 3: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_ui_static.py -v`
Expected: FAIL — assets/function/strings missing

- [ ] **Step 4: Implement `render_slack_channel` in `app/streamlit_app.py`**

Add near the other render helpers (e.g. after `render_incident_command_center`). Imports at top of file: `from src.incident.slack import filter_messages, channel_name`.

```python
def render_slack_channel(incident: dict, messages: list[dict]) -> None:
    import base64
    logo_path = ROOT / "app" / "assets" / "slack-logo.svg"
    logo_tag = ""
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_tag = f'<img src="data:image/svg+xml;base64,{b64}" width="22" style="vertical-align:middle"/>'

    header_cols = st.columns([3, 2])
    with header_cols[0]:
        st.markdown(f"{logo_tag} **{channel_name(incident)}**", unsafe_allow_html=True)
    with header_cols[1]:
        search = st.text_input("Search messages", key="slack_search",
                               placeholder="Search messages (text, author, phase)")

    visible = filter_messages(messages, search)
    with st.container(height=420):  # fixed-height scrollable feed
        for m in visible:
            st.markdown(
                f"{m.get('avatar','💬')} **{m.get('author','')}** "
                f"`{m.get('phase','')}` · {m.get('ts','')}  \n{m.get('text','')}"
            )
    st.caption(f"{len(visible)} / {len(messages)} messages")
```

- [ ] **Step 5: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_ui_static.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add app/assets/slack-logo.svg app/streamlit_app.py tests/test_incident_ui_static.py
git -c commit.gpgsign=false commit -m "feat(incident): add Slack channel render helper with logo, scroll, and search"
```

---

### Task 15: Wire the Incident Response section into the app

**Files:**
- Modify: `app/streamlit_app.py` (add `render_incident_response_simulation` + a `st.expander` section in the main script)
- Test: `tests/test_incident_ui_static.py` (extend)

Adds a section with: scenario picker (`load_scenarios`) **or** free-text operator input (copilot), a Run button, timed streaming playback (`stream_incident` with `time.sleep` between phase deltas), and the Slack channel render. HITL gates surface as `st.button` approvals via the `approve` callback bridged through `st.session_state`.

- [ ] **Step 1: Extend the static test**

```python
# add to tests/test_incident_ui_static.py
def test_incident_section_wired():
    assert "def render_incident_response_simulation(" in APP
    assert "render_incident_response_simulation()" in APP   # called in main script
    assert "Incident Response Simulation" in APP            # expander title
    assert "stream_incident(" in APP                        # timed playback driver
    assert "load_scenarios(" in APP                         # scenario picker
    assert "time.sleep(" in APP                             # timed streaming pacing
```

- [ ] **Step 2: Run it (expect fail)**

Run: `python -m pytest tests/test_incident_ui_static.py::test_incident_section_wired -v`
Expected: FAIL

- [ ] **Step 3: Implement in `app/streamlit_app.py`**

Add imports at top: `from src.incident.scenarios import load_scenarios, get_scenario`, `from src.incident.state import new_incident`, `from src.incident.supervisor import stream_incident`, `from src.incident.graph_lookup import GraphContext`. Then:

```python
def render_incident_response_simulation() -> None:
    st.caption("Hierarchical multi-agent incident simulation grounded in the knowledge graph.")
    scenarios = load_scenarios()
    mode = st.radio("Input mode", ["Scripted scenario", "Operator (copilot)"], horizontal=True,
                    key="inc_mode")

    if mode == "Scripted scenario":
        labels = [f"{s['title']} ({s['severity']})" for s in scenarios]
        idx = st.selectbox("Scenario", range(len(scenarios)), format_func=lambda i: labels[i],
                           key="inc_scenario")
        chosen = scenarios[idx]
        state = new_incident(chosen["incident_id"], chosen["title"], chosen["severity"],
                             chosen["affected_services"], chosen["signal"])
        state["incident"]["recovered"] = chosen.get("recovered", True)
    else:
        signal = st.text_area("Describe the incident", key="inc_signal",
                              placeholder="e.g. Billing service returning 500s after deploy")
        severity = st.selectbox("Severity", ["SEV1", "SEV2", "SEV3"], key="inc_sev")
        service = st.text_input("Primary affected service", key="inc_service",
                                placeholder="Billing Service")
        state = new_incident("incident:adhoc", signal[:60] or "Ad-hoc Incident",
                             severity, [service] if service else [], signal)
        state["incident"]["recovered"] = True

    if st.button("Run incident simulation", key="inc_run"):
        use_real_llm = env_flag("INCIDENT_USE_LLM", False)
        llm = None
        if use_real_llm:
            from src.hybrid_rag import get_llm
            llm = get_llm()
        ctx = GraphContext(use_neo4j=env_flag("INCIDENT_USE_NEO4J", False))
        feed = st.empty()
        collected: list[dict] = []
        for phase, messages in stream_incident(state, llm=llm, ctx=ctx,
                                                use_vector=env_flag("INCIDENT_USE_VECTOR", False),
                                                approve=lambda phase: True,
                                                thread_id=f"ui-{state['incident']['id']}"):
            collected.extend(messages)
            with feed.container():
                render_slack_channel(state["incident"], collected)
            time.sleep(0.6)  # timed streaming playback pacing
        st.success("Incident resolved — postmortem generated.")
```

Then add the section to the main script (near the other expanders, e.g. after the "Ask NexusGraph" block):

```python
with st.expander("Incident Response Simulation", expanded=True):
    render_incident_response_simulation()
```

> NOTE: HITL is auto-approved in v1 UI (`approve=lambda phase: True`) so streaming playback runs end-to-end; a follow-up can replace the callback with `st.button`-gated approval stored in `st.session_state`. `env_flag` already exists in the app. Real LLM/Neo4j/vector are opt-in via env flags so the default demo stays deterministic and offline.

- [ ] **Step 4: Run it (expect pass)**

Run: `python -m pytest tests/test_incident_ui_static.py -v`
Expected: PASS (all)

- [ ] **Step 5: Smoke-test import (catches syntax/import errors without launching Streamlit)**

Run: `python -c "import ast; ast.parse(open('app/streamlit_app.py').read()); print('parse-ok')"`
Expected: `parse-ok`

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add app/streamlit_app.py tests/test_incident_ui_static.py
git -c commit.gpgsign=false commit -m "feat(incident): wire Incident Response Simulation section into Streamlit app"
```

---

## Phase 4 — End-to-End Integration

### Task 16: Scripted-scenario integration test

**Files:**
- Test: `tests/test_incident_integration.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_incident_integration.py
from src.incident.scenarios import get_scenario
from src.incident.state import new_incident
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident

def test_playback_scenario_end_to_end():
    s = get_scenario("playback-latency-sev1")
    state = new_incident(s["incident_id"], s["title"], s["severity"],
                         s["affected_services"], s["signal"])
    state["incident"]["recovered"] = True
    final = run_incident(state, llm=None, ctx=GraphContext(use_neo4j=False),
                         use_vector=False, thread_id="it1")

    phases = [e["phase"] for e in final["timeline"]]
    for expected in ["declare", "triage", "diagnose", "mitigate", "resolve", "postmortem"]:
        assert expected in phases, f"missing phase {expected}"

    assert final["findings"]["severity"] == "SEV1"
    assert final["findings"]["runbook"]["id"].startswith("runbook:")
    assert final["findings"]["slo_recovered"] is True
    assert "# Postmortem" in final["findings"]["postmortem_md"]
    assert final["slack_messages"][0]["role"] == "bot"  # incident bot opens the channel
```

- [ ] **Step 2: Run it (expect pass — all units already implemented)**

Run: `python -m pytest tests/test_incident_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run the full incident suite + existing suite (no regressions)**

Run: `python -m pytest tests/test_incident_*.py -v && python -m pytest tests/ -q`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git -c commit.gpgsign=false add tests/test_incident_integration.py
git -c commit.gpgsign=false commit -m "test(incident): add end-to-end scripted scenario integration test"
```

---

## Self-Review

**Spec coverage:**
- Hierarchical supervisor-over-phase-subgraphs → Tasks 6–12 ✓
- Six lifecycle phases with role agents → Tasks 6–11 ✓
- Both sim + copilot entry → Task 15 (scenario picker + operator input) ✓
- Human-in-the-loop gates → Task 12 (`interrupt_before`) ✓
- Graph + scripted scenarios, read-only grounding → Tasks 1, 4 ✓
- Simulated Slack channel: real logo, scroll, search (text/author/phase), timed playback → Tasks 3, 13, 14, 15 ✓
- Reuse existing stack (get_llm, query_graph_with_retry, vector_query, CSV fallback, Streamlit) → Tasks 4, 8, 12, 15 ✓
- Testing strategy (per-subgraph, routing, Slack render, integration) → Tasks 6–16 ✓
- Non-goals respected (no graph writes, no live telemetry, no real Slack API, HITL only) ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. Two `NOTE:` callouts flag external facts to verify (CSV headers, logo download) — both have fallbacks so tests still pass.

**Type/name consistency:** `IncidentState`, `emit()`, `phrase()`, `GraphContext`, `build_<phase>_subgraph`, `build_incident_graph`, `run_incident`, `stream_incident`, `filter_messages`, `channel_name`, `event_to_slack_message`, finding keys (`severity`, `owner`, `oncall`, `impact`, `runbook`, `rca`, `mitigation_plan`, `escalation`, `slo_recovered`, `postmortem_md`, `action_items`) are consistent across all tasks.
