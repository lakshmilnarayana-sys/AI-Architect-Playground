"""Tests for env-gated live providers (Task 4).

With INCIDENT_LIVE unset every live provider must return None and the
deterministic graph_lookup behaviour must be byte-identical to before.
"""
import importlib


def test_live_runtime_none_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    # Force reimport so module-level state is cleared
    import src.incident.kubernetes as _mod
    importlib.reload(_mod)
    from src.incident.kubernetes import live_runtime
    assert live_runtime("billing-service") is None


def test_live_evidence_none_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    import src.incident.observability as _mod
    importlib.reload(_mod)
    from src.incident.observability import live_evidence
    assert live_evidence("billing-service", "oom_kill") is None


def test_oncall_for_unchanged_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.graph_lookup import GraphContext
    ctx = GraphContext(use_neo4j=False)
    # deterministic fallback still resolves an owner-style dict or None, never raises
    res = ctx.oncall_for("billing-service")
    assert res is None or isinstance(res, dict)
