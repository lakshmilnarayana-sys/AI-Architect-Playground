"""Live multi-pane demo dashboard for the incident agent — ONE process, ONE terminal.

Splits the terminal (via `rich`) into a header + four live panes:

    ┌─ incident summary · elapsed · progress ─────────────────────────────┐
    │                          │ ☸  Kubernetes & Metrics (live)           │
    │   🤖 Agent Reasoning      │ 🔌 Integrations: Slack · Jira · On-call   │
    │   (streams in by phase)  │ 📢 Status Page (HITL-approved per stage) │
    └──────────────────────────────────────────────────────────────────────┘

- Agent reasoning streams in phase by phase with synthetic pacing.
- Kubernetes/Prometheus panes poll the LIVE cluster each tick.
- At each phase boundary the agent proposes a public Status-Page update that a human
  APPROVES (HITL) before it publishes — on a TTY you press [a] to approve, [q] to quit.
- At the resolve stage the dashboard applies the remediation (clears the fault) and then
  WAITS, polling p95, until the SLO genuinely recovers before publishing "Resolved".
- It does NOT exit on its own: the final frame stays up until you press [q] / Ctrl-C, so
  you can screen-capture the complete end state.

    INCIDENT_LIVE=true SLACK_MOCK_URL=... JIRA_MOCK_URL=... ONCALL_REGISTRY_URL=... \
    PROMETHEUS_URL=... KUBE_CONTEXT=kind-streamflix \
    .venv/bin/python -m src.incident.demo_dashboard --service billing-service --failure-mode oom_kill
"""
from __future__ import annotations

import argparse
import json
import os
import random
import select
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.incident.run import run_for_service
from src.incident.slack import channel_name, slugify
from src.incident.supervisor import _dedupe_events

REPO_ROOT = Path(__file__).resolve().parents[2]
FAULT_SCRIPT = REPO_ROOT / "platform" / "scripts" / "inject_fault.sh"
KIND_MARK = {"message": "💬", "action": "⚙️", "gate": "✅", "finding": "🔎"}
PHASE_STYLE = {
    "declare": "bold magenta", "triage": "bold yellow", "diagnose": "bold cyan",
    "mitigate": "bold blue", "resolve": "bold green", "postmortem": "bold white",
}
# Public status-page update proposed at each phase (label, text-template). HITL-gated.
PHASE_STATUS = {
    "declare":    ("🔴 Investigating", "We are investigating an issue affecting {svc}."),
    "triage":     ("🟠 Identified", "Issue isolated to {svc}; on-call engaged and incident channel open."),
    "diagnose":   ("🟠 Identified", "Root cause identified ({fm}) on {svc}; preparing mitigation."),
    "mitigate":   ("🟡 Monitoring", "Mitigation applied to {svc}; monitoring for recovery."),
    "resolve":    ("🟢 Resolved", "{svc} has recovered and the SLO is back within target."),
    "postmortem": ("🟢 Resolved", "Postmortem published for {svc}; follow-up actions are tracked."),
}


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


def _get_json(url: str, timeout: float = 1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode() or "null")
    except Exception:
        return None


def _post_json(url: str, payload: dict, timeout: float = 1.5):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _short(service: str) -> str:
    return service[:-len("-service")] if service.endswith("-service") else service


class KeyReader:
    """Non-blocking single-key reader; no-op (and not enabled) when stdin isn't a TTY."""
    def __init__(self):
        self.enabled = sys.stdin.isatty()
        self._old = None

    def __enter__(self):
        if self.enabled:
            try:
                import termios, tty
                self._old = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                self.enabled = False
        return self

    def get(self):
        if not self.enabled:
            return None
        try:
            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1)
        except Exception:
            return None
        return None

    def __exit__(self, *a):
        if self.enabled and self._old is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old)
            except Exception:
                pass


# ---- live pollers ----------------------------------------------------------

BAD_STATES = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "Error",
              "OOMKilled", "Pending", "ContainerCreating"}


def poll_pods(service: str) -> list[dict]:
    """Return each pod's CURRENT container state (so an OOMKilled pod that has restarted
    back to Running shows 'Running', not its stale lastState reason)."""
    ctx = os.getenv("KUBE_CONTEXT", "kind-streamflix")
    try:
        out = subprocess.run(
            ["kubectl", "--context", ctx, "-n", "streamflix-prod", "get", "pods",
             "-l", f"app={service}", "-o", "json"],
            capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return []
        rows = []
        for p in json.loads(out.stdout).get("items", []):
            name = p["metadata"]["name"]
            phase = p.get("status", {}).get("phase", "?")
            restarts, current, last_term = 0, phase, None
            for cs in p.get("status", {}).get("containerStatuses", []) or []:
                restarts = max(restarts, int(cs.get("restartCount", 0)))
                state = cs.get("state", {})
                if "running" in state:
                    current = "Running"
                elif "waiting" in state:
                    current = state["waiting"].get("reason", "Waiting")
                elif "terminated" in state:
                    current = state["terminated"].get("reason", "Terminated")
                last_term = (cs.get("lastState", {}).get("terminated") or {}).get("reason")
            rows.append({"name": name, "current": current,
                         "restarts": str(restarts), "last_term": last_term})
        return rows
    except Exception:
        return []


def prom_p95(service: str):
    base = _env("PROMETHEUS_URL", "http://localhost:9090")
    q = (f'histogram_quantile(0.95,sum by (le)(rate('
         f'http_request_duration_seconds_bucket{{service="{service}"}}[1m])))')
    d = _get_json(f"{base}/api/v1/query?query={urllib.parse.quote(q)}")
    try:
        res = (d or {}).get("data", {}).get("result", [])
        if res:
            v = float(res[0]["value"][1])
            if v == v:  # not NaN
                return v
    except Exception:
        pass
    return None


def fault_async(service: str, mode: str, value: float, ttl: int, flag: dict, key: str) -> None:
    def _work():
        try:
            subprocess.run(["bash", str(FAULT_SCRIPT), _short(service), mode,
                            str(value), str(ttl)],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass
        flag[key] = True
    threading.Thread(target=_work, daemon=True).start()


def _fmt_latency(v) -> str:
    """Sub-second latencies read clearer in ms; 1s+ stays in seconds."""
    if v is None:
        return "?"
    return f"{v * 1000:.0f}ms" if v < 1.0 else f"{v:.2f}s"


_SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return _SPARK[0] * len(vals)
    return "".join(_SPARK[min(7, int((v - lo) / (hi - lo) * 7))] for v in vals)


# ---- panels ----------------------------------------------------------------

def header_panel(incident, elapsed, shown, total, footer) -> Panel:
    t = Table.grid(expand=True)
    t.add_column(justify="left"); t.add_column(justify="right")
    left = Text.assemble(("INCIDENT  ", "bold white"),
                         (f"{incident.get('severity','?')} ", "bold red"),
                         (f"{incident.get('title','')}", "white"))
    t.add_row(left, Text(f"elapsed {elapsed:4.0f}s   step {shown}/{total}", style="dim"))
    t.add_row(Text(footer, style="bold cyan"), Text(""))
    return Panel(t, style="white", title="🎬 StreamFlix Incident — live", title_align="left")


def trace_panel(steps, shown, thinking) -> Panel:
    body = Table.grid(padding=(0, 1)); body.add_column()
    last = None
    for e in steps[:shown]:
        ph = e.get("phase", "")
        if ph != last:
            body.add_row(Text(f"── {ph.upper()} ──", style=PHASE_STYLE.get(ph, "bold")))
            last = ph
        mark = KIND_MARK.get(e.get("kind", ""), "•")
        body.add_row(Text(f"  {mark} {e.get('actor','?')}: {e.get('text','')}", style="white"))
    if thinking:
        body.add_row(Text(f"  {thinking}", style="dim italic"))
    return Panel(body, title="🤖 Agent Reasoning", title_align="left", border_style="cyan")


def k8s_panel(service, pods, p95_hist, recovering, recovered, pod_mode, breached) -> Panel:
    tbl = Table(expand=True, show_edge=False)
    tbl.add_column("pod", style="dim", overflow="fold")
    tbl.add_column("status"); tbl.add_column("restarts", justify="right")
    if not pods:
        tbl.add_row("(no pods / kubectl n/a)", "", "")
    for p in pods:
        cur = p["current"]
        st = "red" if cur in BAD_STATES else "green"
        last = p["last_term"]
        # don't surface a meaningless "(last: Unknown)" — only show a real prior termination
        suffix = f"  (last: {last})" if cur == "Running" and last and last != "Unknown" else ""
        tbl.add_row(p["name"], Text(cur + suffix, style=st), p["restarts"])

    cur_p95 = next((v for v in reversed(p95_hist) if v is not None), None)
    peak = max([v for v in p95_hist if v is not None], default=None)
    spark = sparkline(list(p95_hist))
    p95_line = Text("\np95 ", style="bold")
    p95_line.append(Text(spark + "  ", style="cyan"))
    if cur_p95 is not None:
        col = "green" if cur_p95 < 0.5 else "yellow"
        p95_line.append(Text(f"peak {_fmt_latency(peak)} → now {_fmt_latency(cur_p95)}", style=col))
    else:
        p95_line.append(Text("(no traffic signal)", style="dim"))

    sli = ("pods Running, restarts stable" if pod_mode else "p95 back within target")
    if recovered and breached:
        slo = Text(f"\nSLO: ✅ recovered — {sli}", style="bold green")
    elif recovered and not breached:
        # We reached the resolve stage but never actually observed the SLI degrade — be honest.
        slo = Text("\nSLO: ✓ no breach observed (fault did not degrade the live SLI this run)",
                   style="bold yellow")
    elif recovering:
        slo = Text("\nSLO: ⏳ verifying recovery (mitigation applied)…", style="bold yellow")
    elif breached:
        slo = Text("\nSLO: 🔴 breached — incident active", style="bold red")
    else:
        slo = Text("\nSLO: monitoring — no breach yet", style="dim")
    return Panel(Group(tbl, p95_line, slo), title="☸  Kubernetes & Metrics (live)",
                 title_align="left", border_style="magenta")


def integrations_panel(incident, flags) -> Panel:
    """Always shows all three integrations (On-call · Slack · Jira), polled live, with a
    placeholder until each is active — so the full picture is visible in the terminal."""
    svc = (incident.get("affected_services") or ["?"])[0]
    g = Table.grid(padding=(0, 1)); g.add_column()

    # On-call
    if flags.get("oncall"):
        oc = _get_json(f"{_env('ONCALL_REGISTRY_URL','http://localhost:18102')}/oncall/{svc}") or {}
        g.add_row(Text("📟 On-call paged", style="bold green"))
        g.add_row(Text(f"   {oc.get('schedule','?')} · {oc.get('team','?')}", style="white"))
    else:
        g.add_row(Text("📟 On-call: pending…", style="dim"))

    # Slack
    if flags.get("slack"):
        ch = channel_name(incident)
        msgs = _get_json(f"{_env('SLACK_MOCK_URL','http://localhost:18100')}/channels/{slugify(ch)}") or []
        seen, uniq = set(), []
        for m in msgs:
            k = (m.get("author"), m.get("text"))
            if k not in seen:
                seen.add(k); uniq.append(m)
        g.add_row(Text(f"💬 Slack {ch}", style="bold green"))
        for m in uniq[-2:]:
            g.add_row(Text(f"   {m.get('author','?')}: {m.get('text','')[:42]}", style="dim"))
    else:
        g.add_row(Text("💬 Slack: pending…", style="dim"))

    # Jira — always polled; shows the ticket as soon as one exists
    issues = _get_json(f"{_env('JIRA_MOCK_URL','http://localhost:18101')}/issues") or []
    if issues:
        g.add_row(Text(f"🎫 Jira ({len(issues)} ticket{'s' if len(issues) != 1 else ''})",
                       style="bold green"))
        for it in issues[-2:]:
            g.add_row(Text(f"   {it.get('key','?')}: "
                           f"{(it.get('fields') or {}).get('summary','')[:38]}", style="white"))
    else:
        g.add_row(Text("🎫 Jira: pending…", style="dim"))

    return Panel(g, title="🔌 Integrations: Slack · Jira · On-call",
                 title_align="left", border_style="green")


def status_panel(published, pending) -> Panel:
    g = Table.grid(padding=(0, 1)); g.add_column()
    for label, text, ts in published:
        g.add_row(Text(f"{label}  ", style="bold").append(Text(text, style="white")))
        g.add_row(Text(f"   ✅ approved {ts}", style="dim green"))
    if pending is not None:
        label, text = pending
        g.add_row(Text(f"{label}  ", style="bold yellow").append(Text(text, style="white")))
        g.add_row(Text("   ⏸ AWAITING APPROVAL — press [a] to approve", style="bold yellow"))
    if not published and pending is None:
        g.add_row(Text("(no public updates yet)", style="dim italic"))
    return Panel(g, title="📢 Status Page (HITL-approved per stage)",
                 title_align="left", border_style="yellow")


# ---- driver ----------------------------------------------------------------

POD_MODES = {"oom_kill", "pod_restart", "image_pull_backoff", "memory_leak", "node_pressure"}


def run(service, failure_mode, severity, delay_min, delay_max,
        auto_approve, gate_pause, recover_threshold, recover_stable,
        recover_timeout, hold_seconds, inject, fault_value) -> None:
    console = Console()
    fm = failure_mode or "issue"
    pod_mode = fm in POD_MODES

    # Make the symptom LIVE for the demo: inject the fault now so the cluster genuinely
    # degrades (p95 climbs for latency faults; pod OOMKills for pod faults) while the agent
    # works — the dashboard then clears it at the mitigate step so recovery is real, not staged.
    inject_flag = {"injected": False}
    if inject and failure_mode:
        console.print(f"[dim]Injecting {failure_mode} on {service} to make the incident live…[/dim]")
        fault_async(service, failure_mode, fault_value, 900, inject_flag, "injected")
        time.sleep(6)  # let the symptom register before we start

    console.print(f"[dim]Running incident for {service} ({failure_mode})…[/dim]")
    final = run_for_service(service, failure_mode=failure_mode, severity=severity)
    incident = final.get("incident", {})
    steps = _dedupe_events(final.get("timeline", []))
    fm = incident.get("failure_mode", failure_mode or "issue")

    # ordered unique phases present in the trace
    phases = []
    for e in steps:
        if e.get("phase") and e["phase"] not in phases:
            phases.append(e["phase"])
    steps_by_phase = {p: [e for e in steps if e.get("phase") == p] for p in phases}

    layout = Layout()
    layout.split_column(Layout(name="header", size=4), Layout(name="body"))
    layout["body"].split_row(Layout(name="trace", ratio=3), Layout(name="right", ratio=2))
    layout["right"].split_column(Layout(name="k8s"), Layout(name="integrations"), Layout(name="status"))

    start = time.time()
    shown = 0                  # flat count of revealed steps (for trace + counter)
    pi = 0                     # current phase index
    in_phase = 0               # steps revealed within current phase
    state = "REVEAL"           # REVEAL | RECOVER | GATE | HOLD
    next_reveal = start
    published, pending = [], None
    recover_done = False
    recover_started = None
    clear_flag = {"cleared": False}
    last_poll, cache = 0.0, {"pods": [], "p95": None}
    p95_hist = deque(maxlen=48)
    breached = False           # has the SLI actually degraded at any point? (honesty gate)
    gate_entered = None

    def flags_now():
        f = {"oncall": False, "slack": False, "jira": False}
        for e in steps[:shown]:
            tx = e.get("text", "").lower()
            if "paging on-call" in tx: f["oncall"] = True
            if "firehydrant" in tx or "slack channel" in tx or "declares" in tx: f["slack"] = True
            if "jira" in tx: f["jira"] = True
        return f

    def publish(phase):
        label, tmpl = PHASE_STATUS.get(phase, ("ℹ️ Update", "{svc} update."))
        text = tmpl.format(svc=service, fm=fm)
        published.append((label, text, time.strftime("%H:%M:%S")))
        _post_json(f"{_env('SLACK_MOCK_URL','http://localhost:18100')}/api/chat.postMessage",
                   {"channel": "#status-page", "text": f"{label} — {text}", "username": "status-page"})

    with KeyReader() as keys, Live(layout, console=console, refresh_per_second=8, screen=True):
        while True:
            now = time.time()
            key = keys.get()
            if key in ("q", "Q") and state == "HOLD":
                break

            recovering = (state == "RECOVER")
            footer = "press [a] approve · [q] quit"

            if state == "REVEAL":
                cur = steps_by_phase[phases[pi]]
                if in_phase < len(cur) and now >= next_reveal:
                    in_phase += 1; shown += 1
                    next_reveal = now + random.uniform(delay_min, delay_max)
                if in_phase >= len(cur):
                    if phases[pi] == "resolve" and not recover_done:
                        state = "RECOVER"; recover_started = now
                        fault_async(service, "clear", 0, 0, clear_flag, "cleared")
                    else:
                        state = "GATE"; gate_entered = now
                        pending = (PHASE_STATUS.get(phases[pi], ("ℹ️", "{svc}"))[0],
                                   PHASE_STATUS.get(phases[pi], ("", "{svc}"))[1].format(svc=service, fm=fm))

            elif state == "RECOVER":
                footer = "applying remediation · verifying SLO recovery…"
                elapsed_r = now - recover_started
                pods = cache.get("pods") or []
                cur_p95 = next((v for v in reversed(p95_hist) if v is not None), None)
                peak = max([v for v in p95_hist if v is not None], default=None)
                if pod_mode:
                    # SLI for a pod-failure incident: pods back to Running and stable.
                    healthy = bool(pods) and all(p["current"] not in BAD_STATES for p in pods)
                    ok = clear_flag["cleared"] and healthy and elapsed_r > recover_stable
                else:
                    # SLI for a latency/throttle incident: p95 drops below target OR falls to
                    # half its peak (handles services whose baseline is above the flat target).
                    ok = (clear_flag["cleared"] and cur_p95 is not None and
                          (cur_p95 < recover_threshold or (peak and cur_p95 <= peak * 0.5)))
                if ok or elapsed_r > recover_timeout:
                    recover_done = True
                    state = "GATE"; gate_entered = now
                    pending = (PHASE_STATUS["resolve"][0],
                               PHASE_STATUS["resolve"][1].format(svc=service, fm=fm))

            elif state == "GATE":
                approve = (key in ("a", "A", "\r", "\n", " ")) or \
                          (auto_approve and (now - gate_entered) > gate_pause)
                if approve and pending is not None:
                    publish(phases[pi]); pending = None
                    pi += 1
                    if pi >= len(phases):
                        state = "HOLD"
                    else:
                        in_phase = 0; state = "REVEAL"; next_reveal = now

            # throttled live polling
            if now - last_poll > 1.2:
                cache["pods"] = poll_pods(service)
                cache["p95"] = prom_p95(service)
                p95_hist.append(cache["p95"])
                # record a real breach (so "recovered" is only ever claimed after one)
                if pod_mode:
                    if any(p["current"] in BAD_STATES for p in cache["pods"]):
                        breached = True
                elif cache["p95"] is not None and cache["p95"] > recover_threshold:
                    breached = True
                last_poll = now

            if state == "HOLD":
                footer = "✅ incident resolved — press [q] or Ctrl-C to exit (frame held for capture)"

            layout["header"].update(header_panel(incident, now - start, shown, len(steps), footer))
            layout["trace"].update(trace_panel(steps, shown,
                                                "…thinking" if state == "REVEAL" and shown < len(steps) else None))
            layout["k8s"].update(k8s_panel(service, cache["pods"], list(p95_hist),
                                           recovering, recover_done, pod_mode, breached))
            layout["integrations"].update(integrations_panel(incident, flags_now()))
            layout["status"].update(status_panel(published, pending))

            if state == "HOLD" and hold_seconds and (now - start) > hold_seconds and not keys.enabled:
                break  # non-interactive safety exit
            try:
                time.sleep(0.15)
            except KeyboardInterrupt:
                break

    jira = (final.get("findings") or {}).get("jira_issue") or {}
    console.print(f"[bold green]Incident complete[/bold green] — phase={final.get('phase')} "
                  f"· jira={jira.get('key','(n/a)')} · {len(steps)} agent steps · "
                  f"{len(published)} status updates published")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", required=True)
    ap.add_argument("--failure-mode", default=None)
    ap.add_argument("--severity", default="SEV2")
    ap.add_argument("--delay-min", type=float, default=1.0)
    ap.add_argument("--delay-max", type=float, default=5.0)
    ap.add_argument("--auto-approve", action="store_true",
                    help="auto-approve each HITL gate after --gate-pause seconds (no keypress)")
    ap.add_argument("--gate-pause", type=float, default=2.5)
    ap.add_argument("--recover-threshold", type=float, default=0.5,
                    help="p95 seconds = recovered (latency/throttle faults)")
    ap.add_argument("--recover-stable", type=float, default=8.0,
                    help="seconds pods must stay Running to count as recovered (pod faults)")
    ap.add_argument("--recover-timeout", type=float, default=90.0)
    ap.add_argument("--hold-seconds", type=float, default=20.0,
                    help="non-interactive only: seconds to hold the final frame before auto-exit")
    ap.add_argument("--no-inject", dest="inject", action="store_false",
                    help="don't inject the fault (assume it's already active in the cluster)")
    ap.add_argument("--fault-value", type=float, default=3.0,
                    help="intensity for the injected fault (e.g. cpu_throttle VALUE)")
    ap.set_defaults(inject=True)
    a = ap.parse_args()
    # Non-TTY (piped / CI) can't read keypresses → force auto-approve so it still completes.
    auto = a.auto_approve or not sys.stdin.isatty()
    run(a.service, a.failure_mode, a.severity, a.delay_min, a.delay_max,
        auto, a.gate_pause, a.recover_threshold, a.recover_stable,
        a.recover_timeout, a.hold_seconds, a.inject, a.fault_value)


if __name__ == "__main__":
    main()
