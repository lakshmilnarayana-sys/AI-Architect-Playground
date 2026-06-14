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
