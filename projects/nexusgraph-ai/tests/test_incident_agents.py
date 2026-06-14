from src.incident.agents import emit, phrase


class FakeLLM:
    def invoke(self, prompt):
        class R:
            content = "LLM-PHRASED"
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
