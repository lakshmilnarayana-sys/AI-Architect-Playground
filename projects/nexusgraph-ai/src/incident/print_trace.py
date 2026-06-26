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
import random
import time

from src.incident.run import run_for_service
from src.incident.supervisor import _dedupe_events

PHASE_ORDER = ["declare", "triage", "diagnose", "mitigate", "resolve", "postmortem"]
KIND_MARK = {"message": "💬", "action": "⚙️", "gate": "✅", "finding": "🔎"}


def print_trace(
    service: str,
    failure_mode: str | None,
    severity: str,
    demo: bool = False,
    delay_min: float = 1.0,
    delay_max: float = 5.0,
) -> dict:
    # Demo-only pacing: pause between printed steps so the trace streams out as if the
    # agent were working through each phase live. This is PRESENTATION ONLY — the pipeline
    # and the evaluation run untouched and fast; the delay is never inside the agent.
    def _pace() -> None:
        if demo:
            time.sleep(random.uniform(delay_min, delay_max))

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
        print(f"\n── {phase.upper()} ──", flush=True)
        for e in steps:
            _pace()
            mark = KIND_MARK.get(e.get("kind", ""), "•")
            actor = e.get("actor", "?")
            text = e.get("text", "")
            print(f"  {mark} {actor:30} {text}", flush=True)

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
    ap.add_argument("--demo", action="store_true",
                    help="stream steps with a synthetic pause between them (presentation only)")
    ap.add_argument("--delay-min", type=float, default=1.0, help="min seconds between steps in --demo")
    ap.add_argument("--delay-max", type=float, default=5.0, help="max seconds between steps in --demo")
    a = ap.parse_args()
    print_trace(a.service, a.failure_mode, a.severity,
                demo=a.demo, delay_min=a.delay_min, delay_max=a.delay_max)


if __name__ == "__main__":
    main()
