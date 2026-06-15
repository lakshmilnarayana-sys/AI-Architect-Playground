from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_ui_journey_test(*, service_name: str, target_url: str, output_path: Path, config: dict[str, Any] | None = None) -> Path:
    config = config or {}
    journey_name = config.get("journey_name", config.get("name", "default-ui"))
    path = config.get("path", "/")
    action_selector = config.get("action_selector", "button[type=submit],button")
    wait_selector = config.get("wait_selector", "body")
    steps = config.get("steps") or [
        {"action": "goto", "path": path},
        {"action": "wait_for_selector", "selector": wait_selector},
        {"action": "click", "selector": action_selector},
    ]
    web_vitals = bool(config.get("web_vitals", True))
    screenshot_on_error = bool(config.get("screenshot_on_error", False))
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
JOURNEY_NAME = {journey_name!r}
PATH = {path!r}
ACTION_SELECTOR = {action_selector!r}
WAIT_SELECTOR = {wait_selector!r}
JOURNEY_STEPS = {steps!r}
WEB_VITALS = {web_vitals!r}
SCREENSHOT_ON_ERROR = {screenshot_on_error!r}
MAX_RETAINED_LATENCIES = 10000


def _url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return TARGET_URL + path


def _run_step(page, step: dict) -> None:
    action = step.get("action", "goto")
    if action == "goto":
        page.goto(_url(step.get("path", PATH)), wait_until=step.get("wait_until", "networkidle"), timeout=int(step.get("timeout_ms", 30000)))
    elif action == "click":
        page.locator(step["selector"]).first.click(timeout=int(step.get("timeout_ms", 5000)))
    elif action == "fill":
        page.fill(step["selector"], str(step.get("value", "")), timeout=int(step.get("timeout_ms", 5000)))
    elif action == "wait_for_selector":
        page.wait_for_selector(step["selector"], timeout=int(step.get("timeout_ms", 5000)))
    elif action == "press":
        page.press(step["selector"], step.get("key", "Enter"), timeout=int(step.get("timeout_ms", 5000)))
    elif action == "wait":
        page.wait_for_timeout(int(step.get("milliseconds", step.get("ms", 250))))
    else:
        raise ValueError(f"unsupported UI journey action: {{action}}")


def _browser_metrics(page) -> dict:
    if not WEB_VITALS:
        return {{}}
    return page.evaluate("""() => {{
        const nav = performance.getEntriesByType('navigation')[0];
        const paint = performance.getEntriesByType('paint');
        const metric = name => {{
          const item = paint.find(entry => entry.name === name);
          return item ? item.startTime : 0;
        }};
        const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
        const lcp = lcpEntries.length ? lcpEntries[lcpEntries.length - 1].startTime : 0;
        return {{
          dom_content_loaded_ms: nav ? nav.domContentLoadedEventEnd : 0,
          load_event_ms: nav ? nav.loadEventEnd : 0,
          first_paint_ms: metric('first-paint'),
          first_contentful_paint_ms: metric('first-contentful-paint'),
          largest_contentful_paint_ms: lcp,
          transfer_size_bytes: nav ? nav.transferSize : 0
        }};
    }}""")


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
                for step in JOURNEY_STEPS:
                    _run_step(page, step)
                browser_metrics.append(_browser_metrics(page))
                requests += 1
            except Exception as exc:
                errors += 1
                requests += 1
                if SCREENSHOT_ON_ERROR:
                    page.screenshot(path=f"ui-error-{{JOURNEY_NAME}}-{{requests}}.png", full_page=True)
            finally:
                if len(latencies_ms) < MAX_RETAINED_LATENCIES:
                    latencies_ms.append((time.perf_counter() - start) * 1000)
        browser.close()
    return [{{"service": SERVICE_NAME, "journey": JOURNEY_NAME, "requests": requests, "errors": errors, "latencies_ms": latencies_ms, "concurrency": concurrency, "browser_metrics": browser_metrics}}]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(run(args.duration_seconds, args.concurrency)))
'''
    )
    return output_path
