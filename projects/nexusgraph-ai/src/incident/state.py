import operator
from typing import Annotated, Optional, TypedDict


class IncidentEvent(TypedDict, total=False):
    ts: str          # ISO-ish "HH:MM:SS"
    phase: str
    actor: str       # display name, e.g. "TriageAgent" or "J. Okafor"
    role: str        # one of ROLE_AVATARS keys (see slack.py)
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
