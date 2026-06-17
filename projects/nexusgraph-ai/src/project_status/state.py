from typing import TypedDict


class ProjectStatusState(TypedDict, total=False):
    project: str
    owner: str
    current_week: str
    current_snapshot: dict
    previous_snapshot: dict
    risks: list[dict]
    blockers: list[dict]
    dependencies: list[dict]
    insights: list[dict]
    overall_status: str
    executive_summary: str
    next_actions: list[str]
