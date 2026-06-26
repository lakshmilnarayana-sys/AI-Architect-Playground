"""Run one incident and print the AI agent's step-by-step trace.

Shows what the multi-agent pipeline actually did — phase by phase, agent by agent —
so it's visible (in a demo or a log) that the AGENT performed the incident response,
distinct from Kubernetes merely restarting the pod.

    .venv/bin/python -m src.incident.print_trace --service billing-service --failure-mode oom_kill

With INCIDENT_LIVE=true + the mock URLs exported, it also posts to Slack/Jira and reads the
live cluster; without them it runs deterministically. Either way the trace is the same shape.
"""
from __future__ import annotations

import argparse

from src.incident.run import run_for_service
from src.incident.supervisor import _dedupe_events

PHASE_ORDER = ["declare", "triage", "diagnose", "mitigate", "resolve", "postmortem"]
KIND_MARK = {"message": "💬", "action": "⚙️", "gate": "✅", "finding": "🔎"}


def print_trace(service: str, failure_mode: str | None, severity: str) -> dict:
    final = run_for_service(service, failure_mode=failure_mode, severity=severity)
    events = _dedupe_events(final.get("timeline", []))

    print("=" * 78)
    print(f"AI INCIDENT-RESPONSE AGENT — trace for {service} (failure_mode={failure_mode})")
    print(f"{len(events)} agent steps across {len(PHASE_ORDER)} phases")
    print("=" * 78)

    by_phase: dict[str, list] = {}
    for e in events:
        by_phase.setdefault(e.get("phase", "other"), []).append(e)

    for phase in PHASE_ORDER + [p for p in by_phase if p not in PHASE_ORDER]:
        steps = by_phase.get(phase)
        if not steps:
            continue
        print(f"\n── {phase.upper()} ──")
        for e in steps:
            mark = KIND_MARK.get(e.get("kind", ""), "•")
            actor = e.get("actor", "?")
            text = e.get("text", "")
            print(f"  {mark} {actor:30} {text}")

    findings = final.get("findings") or {}
    print("\n" + "=" * 78)
    print("KEY OUTPUTS")
    print("=" * 78)
    rca = findings.get("rca")
    runbook = (findings.get("runbook") or {})
    jira = findings.get("jira_issue") or {}
    print(f"  root cause:   {rca or '(n/a)'}")
    print(f"  runbook:      {runbook.get('name') or runbook.get('id') or '(none matched)'}")
    print(f"  jira ticket:  {jira.get('key') or '(not created)'}")
    print(f"  final phase:  {final.get('phase')}")
    return final


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", required=True)
    ap.add_argument("--failure-mode", default=None)
    ap.add_argument("--severity", default="SEV2")
    a = ap.parse_args()
    print_trace(a.service, a.failure_mode, a.severity)


if __name__ == "__main__":
    main()
