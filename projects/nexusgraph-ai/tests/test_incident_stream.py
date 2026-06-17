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
