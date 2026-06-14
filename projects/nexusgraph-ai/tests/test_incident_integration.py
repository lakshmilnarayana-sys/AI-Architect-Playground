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
