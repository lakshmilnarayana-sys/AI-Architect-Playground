"""Agent target wrapper for evaluation.

``run_incident_target(inputs)`` takes one golden-dataset input row, drives the
real multi-agent LangGraph pipeline, and flattens the final state into a flat,
scorable dict the evaluators can read. It never raises: a crash is captured as
``{"error": ...}`` so a single bad case can't abort the whole eval run.

Env flags (mirror the Streamlit app):
    INCIDENT_USE_LLM     -> use a real LLM for RCA/mitigation phrasing (default off)
    INCIDENT_USE_NEO4J   -> query the live graph (default off -> CSV/YAML fallback)
    INCIDENT_USE_VECTOR  -> pull vector evidence (default off)
"""
from __future__ import annotations

import os
import time
import uuid

from src.incident.state import new_incident
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident, _dedupe_events, _dedupe_records


def _flag(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _build_state(inputs: dict):
    state = new_incident(
        inputs["incident_id"],
        inputs.get("title", ""),
        inputs.get("severity", "SEV3"),
        inputs.get("affected_services", []),
        inputs.get("signal", ""),
    )
    inc = state["incident"]
    inc["recovered"] = bool(inputs.get("recovered", True))
    inc["scenario_id"] = inputs.get("scenario_id")
    inc["failure_mode"] = inputs.get("failure_mode")
    inc["simulate_failure"] = bool(inputs.get("simulate_failure"))
    return state


def _maybe_llm():
    if not _flag("INCIDENT_USE_LLM"):
        return None
    from src.hybrid_rag import get_llm
    return get_llm()


def _name(value):
    if isinstance(value, dict):
        return value.get("name")
    return value


def _flatten(final: dict, latency_s: float) -> dict:
    findings = final.get("findings") or {}
    # run_incident returns raw accumulated state; the app only dedupes inside
    # stream_incident, so mirror that here for honest counts.
    timeline = _dedupe_events(final.get("timeline") or [])
    logs = _dedupe_records(final.get("logs") or [])
    observability = _dedupe_records(final.get("observability") or [])
    runtime = findings.get("kubernetes_runtime") or final.get("runtime") or {}

    # Trajectory: identical diagnose text collapses on dedupe, so the reliable
    # rediagnose signal is the attempt counter (1 = no loop, >=2 = loop fired).
    diagnose_attempts = (final.get("incident") or {}).get("_diagnose_attempts", 1)
    phases_seen = sorted({e.get("phase", "") for e in timeline if e.get("phase")})
    present_artifacts = [
        key for key in ("owner", "rca", "mitigation_plan", "postmortem_md", "action_items")
        if findings.get(key)
    ]

    return {
        "error": None,
        "latency_s": round(latency_s, 3),
        # diagnosis
        "active_failure": runtime.get("active_failure"),
        "rca": findings.get("rca"),
        # triage / routing
        "owner_team": _name(findings.get("owner")),
        "oncall_name": _name(findings.get("oncall")),
        "escalation_name": _name(findings.get("escalation")),
        # mitigation
        "mitigation_plan": findings.get("mitigation_plan"),
        # resolution / postmortem
        "slo_recovered": findings.get("slo_recovered"),
        "postmortem_md": findings.get("postmortem_md"),
        "action_items": findings.get("action_items") or [],
        # trajectory
        "diagnose_attempts": diagnose_attempts,
        "phases_seen": phases_seen,
        "present_artifacts": present_artifacts,
        "logs_count": len(logs),
        "observability_count": len(observability),
        "token_usage": final.get("token_usage") or {},
    }


def run_incident_target(inputs: dict) -> dict:
    """Run the pipeline for one dataset row. Returns a flat scorable dict."""
    started = time.perf_counter()
    try:
        state = _build_state(inputs)
        ctx = GraphContext(use_neo4j=_flag("INCIDENT_USE_NEO4J"))
        final = run_incident(
            state,
            llm=_maybe_llm(),
            ctx=ctx,
            use_vector=_flag("INCIDENT_USE_VECTOR"),
            thread_id=f"eval-{uuid.uuid4().hex[:8]}",
        )
        out = _flatten(final, time.perf_counter() - started)
        return out
    except Exception as exc:  # never abort the eval over one bad case
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "latency_s": round(time.perf_counter() - started, 3),
            "active_failure": None,
            "rca": None,
            "owner_team": None,
            "oncall_name": None,
            "escalation_name": None,
            "mitigation_plan": None,
            "slo_recovered": None,
            "postmortem_md": None,
            "action_items": [],
            "diagnose_attempts": 0,
            "phases_seen": [],
            "present_artifacts": [],
            "logs_count": 0,
            "observability_count": 0,
            "token_usage": {},
        }


if __name__ == "__main__":
    import json
    import sys

    from evaluation.incident.build_dataset import build

    cases = build()
    sample = cases[0] if len(sys.argv) < 2 else next(c for c in cases if c["id"] == sys.argv[1])
    print(f"# {sample['id']}  ({sample['metadata']['scenario_type']})")
    out = run_incident_target(sample["inputs"])
    print(json.dumps(out, indent=2, default=str))
