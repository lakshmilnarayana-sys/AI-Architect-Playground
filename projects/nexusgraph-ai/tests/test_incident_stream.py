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


def test_stream_returns_final_state_with_backend_provenance():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    captured = {}

    for _phase, _messages in stream_incident(state, llm=None,
                                             ctx=GraphContext(use_neo4j=False),
                                             use_vector=False,
                                             approve=lambda phase: True,
                                             thread_id="s2",
                                             on_final=lambda final: captured.update(final)):
        pass

    assert captured["_backend_provenance"]["executor"] == "LangGraph StateGraph"
    assert captured["_backend_provenance"]["thread_id"] == "s2"
    assert captured["_backend_provenance"]["source"] == "stream_incident"
    assert captured["findings"]["jira_issue"]["key"].startswith("INC-")


def test_stream_dedupes_replayed_events_in_causal_order():
    state = new_incident(
        "incident:playback-oom-sev1",
        "Playback Latency SEV1",
        "SEV1",
        ["Playback Service"],
        "p99 SLO breach in US-East and OOMKilled pod",
    )
    state["incident"]["simulate_failure"] = True
    state["incident"]["failure_mode"] = "oom_kill"
    state["incident"]["recovered"] = True
    captured = {}
    seen = []

    for _phase, messages in stream_incident(state, llm=None,
                                            ctx=GraphContext(use_neo4j=False),
                                            use_vector=False,
                                            approve=lambda phase: True,
                                            thread_id="s3",
                                            on_final=lambda final: captured.update(final)):
        seen.extend(messages)

    first_eight = [(event["phase"], event["actor"]) for event in captured["timeline"][:8]]
    assert first_eight == [
        ("declare", "Observability Agent"),
        ("declare", "Incident Commander Agent"),
        ("declare", "Severity Classifier"),
        ("triage", "TriageAgent"),
        ("triage", "TriageAgent"),
        ("triage", "TriageAgent"),
        ("triage", "KubernetesAgent"),
        ("triage", "FireHydrant Runbook Automation"),
    ]
    assert len({(m["phase"], m["author"], m["role"], m["text"]) for m in seen}) == len(seen)
