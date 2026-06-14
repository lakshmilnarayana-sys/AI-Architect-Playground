from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_ui_journey_test(*, service_name: str, target_url: str, output_path: Path, config: dict[str, Any] | None = None) -> Path:
    config = config or {}
    path = config.get("path", "/")
    action_selector = config.get("action_selector", "button[type=submit],button")
    wait_selector = config.get("wait_selector", "body")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f'''"""Generated browser/UI performance harness for {service_name}.

This harness uses Playwright when available. If Playwright is not installed, it emits a failed
JSON result instead of crashing so PerfAgent can still produce an evidence-backed report.
"""

import argparse
import json
import time


SERVICE_NAME = {service_name!r}
TARGET_URL = {target_url.rstrip("/")!r}
PATH = {path!r}
ACTION_SELECTOR = {action_selector!r}
WAIT_SELECTOR = {wait_selector!r}
MAX_RETAINED_LATENCIES = 10000


def run(duration_seconds: int, concurrency: int) -> list[dict]:
    started = time.time()
    requests = 0
    errors = 0
    latencies_ms = []
    browser_metrics = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return [{{"requests": 1, "errors": 1, "latencies_ms": [0], "error": f"playwright unavailable: {{exc}}"}}]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        while time.time() - started < duration_seconds:
            start = time.perf_counter()
            try:
                page.goto(TARGET_URL + PATH, wait_until="networkidle", timeout=30000)
                if WAIT_SELECTOR:
                    page.wait_for_selector(WAIT_SELECTOR, timeout=5000)
                if ACTION_SELECTOR:
                    matches = page.locator(ACTION_SELECTOR)
                    if matches.count() > 0:
                        matches.first.click(timeout=5000)
                browser_metrics.append(page.evaluate("""() => {{
                    const nav = performance.getEntriesByType('navigation')[0];
                    const paint = performance.getEntriesByType('paint');
                    const metric = name => {{
                      const item = paint.find(entry => entry.name === name);
                      return item ? item.startTime : 0;
                    }};
                    return {{
                      dom_content_loaded_ms: nav ? nav.domContentLoadedEventEnd : 0,
                      load_event_ms: nav ? nav.loadEventEnd : 0,
                      first_paint_ms: metric('first-paint'),
                      first_contentful_paint_ms: metric('first-contentful-paint'),
                      transfer_size_bytes: nav ? nav.transferSize : 0
                    }};
                }}"""))
                requests += 1
            except Exception:
                errors += 1
                requests += 1
            finally:
                if len(latencies_ms) < MAX_RETAINED_LATENCIES:
                    latencies_ms.append((time.perf_counter() - start) * 1000)
        browser.close()
    return [{{"service": SERVICE_NAME, "requests": requests, "errors": errors, "latencies_ms": latencies_ms, "concurrency": concurrency, "browser_metrics": browser_metrics}}]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run(args.duration_seconds, args.concurrency)))
'''
    )
    return output_path
