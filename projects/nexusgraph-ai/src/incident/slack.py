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
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


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


def post_to_slack(channel: str, text: str, username: str = "incident-bot"):
    """Post to the live slack-mock when INCIDENT_LIVE; else return None (caller renders in-memory)."""
    from src.incident.live_clients import live_enabled, endpoint, http_post_json
    if not live_enabled():
        return None
    return http_post_json(
        f"{endpoint('slack')}/api/chat.postMessage",
        {"channel": channel, "text": text, "username": username},
    )
