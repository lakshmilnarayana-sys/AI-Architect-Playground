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
