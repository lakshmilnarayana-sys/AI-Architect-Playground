"""Live multi-pane demo dashboard for the incident agent — ONE process, ONE terminal.

Splits the terminal (via `rich`) into a header + three live panes:

    ┌─ incident summary · elapsed · progress ─────────────────────────────┐
    │ 🤖 Agent Reasoning   │ ☸  Kubernetes & Metrics │ 🔌 Integrations     │
    └──────────────────────────────────────────────────────────────────────┘

The agent's reasoning trace streams in with synthetic pacing; the Kubernetes and
Prometheus panes poll the LIVE cluster each tick; the Integrations pane reveals the
Slack channel / Jira ticket / on-call as the trace reaches the steps that create them.
No tmux, no second terminal.

    INCIDENT_LIVE=true SLACK_MOCK_URL=... JIRA_MOCK_URL=... ONCALL_REGISTRY_URL=... \
    PROMETHEUS_URL=... KUBE_CONTEXT=kind-streamflix \
    .venv/bin/python -m src.incident.demo_dashboard --service billing-service --failure-mode oom_kill
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
import urllib.parse
import urllib.request

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.incident.run import run_for_service
from src.incident.slack import channel_name, slugify
from src.incident.supervisor import _dedupe_events

KIND_MARK = {"message": "💬", "action": "⚙️", "gate": "✅", "finding": "🔎"}
PHASE_STYLE = {
    "declare": "bold magenta", "triage": "bold yellow", "diagnose": "bold cyan",
    "mitigate": "bold blue", "resolve": "bold green", "postmortem": "bold white",
}


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


def _get_json(url: str, timeout: float = 1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode() or "null")
    except Exception:
        return None


def poll_pods(service: str) -> list[tuple[str, str, str]]:
    ctx = os.getenv("KUBE_CONTEXT", "kind-streamflix")
    try:
        out = subprocess.run(
            ["kubectl", "--context", ctx, "-n", "streamflix-prod", "get", "pods",
             "-l", f"app={service}", "-o", "json"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []
        rows = []
        for p in json.loads(out.stdout).get("items", []):
            name = p["metadata"]["name"]
            phase = p.get("status", {}).get("phase", "?")
            restarts = 0
            reason = phase
            for cs in p.get("status", {}).get("containerStatuses", []) or []:
                restarts = max(restarts, int(cs.get("restartCount", 0)))
                w = (cs.get("state", {}).get("waiting") or {}).get("reason")
                t = (cs.get("lastState", {}).get("terminated") or {}).get("reason")
                reason = w or t or phase
            rows.append((name, reason, str(restarts)))
        return rows
    except Exception:
        return []


def prom_scalar(q: str) -> str:
    base = _env("PROMETHEUS_URL", "http://localhost:9090")
    d = _get_json(f"{base}/api/v1/query?query={urllib.parse.quote(q)}")
    try:
        res = (d or {}).get("data", {}).get("result", [])
        if res:
            return f"{float(res[0]['value'][1]):.3f}"
    except Exception:
        pass
    return "n/a"


# ---- panel builders --------------------------------------------------------

def header_panel(incident: dict, elapsed: float, shown: int, total: int) -> Panel:
    t = Table.grid(expand=True)
    t.add_column(justify="left"); t.add_column(justify="right")
    left = Text.assemble(
        ("INCIDENT  ", "bold white"),
        (f"{incident.get('severity','?')} ", "bold red"),
        (f"{incident.get('title','')}", "white"),
    )
    right = Text(f"elapsed {elapsed:4.0f}s   step {shown}/{total}", style="dim")
    t.add_row(left, right)
    return Panel(t, style="white", title="🎬 StreamFlix Incident — live", title_align="left")


def trace_panel(steps: list[dict], shown: int) -> Panel:
    body = Table.grid(padding=(0, 1)); body.add_column()
    last_phase = None
    for e in steps[:shown]:
        ph = e.get("phase", "")
        if ph != last_phase:
            body.add_row(Text(f"── {ph.upper()} ──", style=PHASE_STYLE.get(ph, "bold")))
            last_phase = ph
        mark = KIND_MARK.get(e.get("kind", ""), "•")
        body.add_row(Text(f"  {mark} {e.get('actor','?')}: {e.get('text','')}", style="white"))
    if shown < len(steps):
        body.add_row(Text("  …thinking", style="dim italic"))
    return Panel(body, title="🤖 Agent Reasoning", title_align="left", border_style="cyan")


def k8s_panel(service: str) -> Panel:
    pods = poll_pods(service)
    tbl = Table(expand=True, show_edge=False)
    tbl.add_column("pod", style="dim", overflow="fold")
    tbl.add_column("status"); tbl.add_column("restarts", justify="right")
    if not pods:
        tbl.add_row("(no pods / kubectl n/a)", "", "")
    for name, status, restarts in pods:
        st = "red" if status in ("OOMKilled", "CrashLoopBackOff", "Error") else "green"
        tbl.add_row(name[-28:], Text(status, style=st), restarts)
    err = prom_scalar(f'sum(rate(http_requests_total{{service="{service}",code=~"5.."}}[1m]))'
                      f'/sum(rate(http_requests_total{{service="{service}"}}[1m]))')
    p95 = prom_scalar(f'histogram_quantile(0.95,sum by (le)(rate('
                      f'http_request_duration_seconds_bucket{{service="{service}"}}[1m])))')
    metrics = Text.assemble(
        ("\nlive metrics  ", "bold"),
        (f"5xx ratio={err}   ", "yellow"),
        (f"p95={p95}s", "yellow"),
    )
    return Panel(Group(tbl, metrics), title="☸  Kubernetes & Metrics (live)",
                 title_align="left", border_style="magenta")


def integrations_panel(incident: dict, flags: dict) -> Panel:
    svc = (incident.get("affected_services") or ["?"])[0]
    g = Table.grid(padding=(0, 1)); g.add_column()

    if flags.get("oncall"):
        oc = _get_json(f"{_env('ONCALL_REGISTRY_URL','http://localhost:18102')}/oncall/{svc}") or {}
        g.add_row(Text("📟 On-call paged", style="bold green"))
        g.add_row(Text(f"   {oc.get('schedule','?')} · {oc.get('team','?')}", style="white"))
    if flags.get("slack"):
        ch = channel_name(incident)
        msgs = _get_json(f"{_env('SLACK_MOCK_URL','http://localhost:18100')}/channels/{slugify(ch)}") or []
        g.add_row(Text(f"\n💬 Slack {ch} ({len(msgs)} msg)", style="bold green"))
        for m in (msgs or [])[:3]:
            g.add_row(Text(f"   {m.get('author','?')}: {m.get('text','')[:46]}", style="dim"))
    if flags.get("jira"):
        issues = _get_json(f"{_env('JIRA_MOCK_URL','http://localhost:18101')}/issues") or []
        g.add_row(Text(f"\n🎫 Jira ({len(issues)} ticket)", style="bold green"))
        for it in (issues or [])[:2]:
            g.add_row(Text(f"   {it.get('key','?')}: "
                           f"{(it.get('fields') or {}).get('summary','')[:40]}", style="white"))
    if not any(flags.values()):
        g.add_row(Text("(waiting for the agent to page/declare…)", style="dim italic"))
    return Panel(g, title="🔌 Integrations: Slack · Jira · On-call",
                 title_align="left", border_style="green")


def _flags_for(steps: list[dict], shown: int) -> dict:
    """Reveal integration sections as the trace reaches the steps that create them."""
    flags = {"oncall": False, "slack": False, "jira": False}
    for e in steps[:shown]:
        text = e.get("text", "").lower()
        if "paging on-call" in text:
            flags["oncall"] = True
        if "firehydrant" in text or "slack channel" in text or "declares" in text:
            flags["slack"] = True
        if "jira" in text:
            flags["jira"] = True
    return flags


def run(service: str, failure_mode: str | None, severity: str,
        delay_min: float, delay_max: float) -> None:
    console = Console()
    console.print(f"[dim]Running incident for {service} ({failure_mode})…[/dim]")
    final = run_for_service(service, failure_mode=failure_mode, severity=severity)
    incident = final.get("incident", {})
    steps = _dedupe_events(final.get("timeline", []))

    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    layout["body"].split_row(
        Layout(name="trace", ratio=2), Layout(name="k8s"), Layout(name="integrations"))

    start = time.time()
    shown = 0
    next_reveal = start  # reveal the first step immediately
    last_poll = 0.0
    cache = {}  # cached panels for the live-polled panes (throttled)

    with Live(layout, console=console, refresh_per_second=8, screen=True):
        while True:
            now = time.time()
            if shown < len(steps) and now >= next_reveal:
                shown += 1
                next_reveal = now + random.uniform(delay_min, delay_max)
            flags = _flags_for(steps, shown)
            if now - last_poll > 1.2:  # throttle the live kubectl/curl polls
                cache["k8s"] = k8s_panel(service)
                cache["integrations"] = integrations_panel(incident, flags)
                last_poll = now
            layout["header"].update(header_panel(incident, now - start, shown, len(steps)))
            layout["trace"].update(trace_panel(steps, shown))
            layout["k8s"].update(cache.get("k8s") or k8s_panel(service))
            layout["integrations"].update(
                cache.get("integrations") or integrations_panel(incident, flags))
            if shown >= len(steps):
                time.sleep(4)  # linger so the final frame is recordable
                break
            time.sleep(0.2)

    jira = (final.get("findings") or {}).get("jira_issue") or {}
    console.print(f"[bold green]Incident complete[/bold green] — phase={final.get('phase')} "
                  f"· jira={jira.get('key','(n/a)')} · {len(steps)} agent steps")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", required=True)
    ap.add_argument("--failure-mode", default=None)
    ap.add_argument("--severity", default="SEV2")
    ap.add_argument("--delay-min", type=float, default=1.0)
    ap.add_argument("--delay-max", type=float, default=5.0)
    a = ap.parse_args()
    run(a.service, a.failure_mode, a.severity, a.delay_min, a.delay_max)


if __name__ == "__main__":
    main()
