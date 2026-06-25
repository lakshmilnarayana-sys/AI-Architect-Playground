"""Poll Alertmanager for active StreamFlix alerts and run the incident pipeline."""
from __future__ import annotations

import time

from src.incident.live_clients import endpoint, http_get_json
from src.incident.run import seed_from_alert
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident

_SEEN: set[str] = set()


def fetch_active_alerts() -> list[dict]:
    data = http_get_json(f"{endpoint('alertmanager')}/api/v2/alerts?active=true")
    return data or []


def _is_streamflix(alert: dict) -> bool:
    return str((alert.get("labels", {}) or {}).get("alertname", "")).startswith("StreamFlix")


def process_once() -> int:
    ran = 0
    for alert in fetch_active_alerts():
        if not _is_streamflix(alert):
            continue
        fp = alert.get("fingerprint") or str(alert.get("labels"))
        if fp in _SEEN:
            continue
        _SEEN.add(fp)
        state = seed_from_alert(alert)
        run_incident(state, ctx=GraphContext(use_neo4j=False), use_vector=False)
        print(f"ran incident for {alert.get('labels', {}).get('alertname')} "
              f"/ {alert.get('labels', {}).get('service') or alert.get('labels', {}).get('pod')}")
        ran += 1
    return ran


def watch(poll_seconds: int = 15, once: bool = False) -> None:
    print(f"watcher polling Alertmanager every {poll_seconds}s (INCIDENT_LIVE recommended)")
    while True:
        try:
            process_once()
        except Exception as exc:  # never die on a transient error
            print(f"watch error: {type(exc).__name__}: {exc}")
        if once:
            return
        time.sleep(poll_seconds)


if __name__ == "__main__":
    watch()
