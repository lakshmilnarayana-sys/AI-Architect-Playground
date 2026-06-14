from __future__ import annotations

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


REQUEST_COUNT = 0
ERROR_COUNT = 0
TOTAL_LATENCY_SECONDS = 0.0


def render_checkout_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PerfAgent Checkout</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #17202a; }
    main { max-width: 1040px; margin: 0 auto; padding: 32px 20px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
    h1 { font-size: 28px; margin: 0; letter-spacing: 0; }
    .shell { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr); gap: 20px; }
    section, aside { background: #ffffff; border: 1px solid #d8dee8; border-radius: 8px; padding: 20px; }
    label { display: block; font-size: 13px; font-weight: 650; margin: 14px 0 6px; }
    input, select { width: 100%; box-sizing: border-box; border: 1px solid #b9c2cf; border-radius: 6px; padding: 10px 12px; font-size: 15px; }
    button { margin-top: 18px; width: 100%; border: 0; border-radius: 6px; background: #1b5e3b; color: white; padding: 12px 14px; font-size: 15px; font-weight: 700; cursor: pointer; }
    button:disabled { background: #7b8794; cursor: wait; }
    .status { min-height: 52px; border-radius: 6px; background: #eef3f8; padding: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; white-space: pre-wrap; }
    .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .metric { border-left: 3px solid #1b5e3b; padding-left: 10px; }
    .metric strong { display: block; font-size: 22px; }
    @media (max-width: 760px) { .shell { grid-template-columns: 1fr; } .metrics { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>PerfAgent Checkout</h1>
      <span>UI performance target</span>
    </header>
    <div class="shell">
      <section>
        <form id="checkout-form" data-perf-target="checkout-submit">
          <label for="customerId">Customer ID</label>
          <input id="customerId" name="customerId" value="cust_ui_1001" autocomplete="off">
          <label for="amount">Amount</label>
          <input id="amount" name="amount" type="number" step="0.01" value="49.99">
          <label for="currency">Currency</label>
          <select id="currency" name="currency">
            <option>GBP</option>
            <option>USD</option>
            <option>EUR</option>
          </select>
          <button id="submit-button" type="submit">Authorize payment</button>
        </form>
      </section>
      <aside>
        <div class="metrics">
          <div class="metric"><strong id="attempts">0</strong><span>Attempts</span></div>
          <div class="metric"><strong id="last-duration">0</strong><span>Last ms</span></div>
          <div class="metric"><strong id="status-code">-</strong><span>Status</span></div>
        </div>
        <h2>Response</h2>
        <div class="status" id="response">No checkout submitted.</div>
      </aside>
    </div>
  </main>
  <script>
    let attempts = 0;
    const form = document.getElementById('checkout-form');
    const button = document.getElementById('submit-button');
    const responseBox = document.getElementById('response');
    const attemptsBox = document.getElementById('attempts');
    const durationBox = document.getElementById('last-duration');
    const statusBox = document.getElementById('status-code');
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name.includes('/api/checkout')) durationBox.textContent = Math.round(entry.duration);
      }
    }).observe({ entryTypes: ['resource'] });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      attempts += 1;
      attemptsBox.textContent = String(attempts);
      const payload = {
        customerId: form.customerId.value,
        amount: Number(form.amount.value),
        currency: form.currency.value
      };
      const started = performance.now();
      const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const body = await res.json();
      statusBox.textContent = String(res.status);
      durationBox.textContent = String(Math.round(performance.now() - started));
      responseBox.textContent = JSON.stringify(body, null, 2);
      button.disabled = false;
    });
  </script>
</body>
</html>
"""


def authorize_checkout(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    missing = [field for field in ["amount", "currency"] if field not in payload]
    if not payload.get("customerId"):
        missing.insert(0, "customerId")
    if missing:
        return 400, {"error": "missing_required_fields", "fields": missing}
    return (
        201,
        {
            "checkoutId": f"chk_ui_{int(time.time() * 1000)}",
            "customerId": payload["customerId"],
            "amount": payload["amount"],
            "currency": payload["currency"],
            "status": "authorized",
            "channel": "ui",
        },
    )


def render_openapi_json() -> str:
    return json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "UI Checkout App", "version": "1.0.0"},
            "paths": {
                "/api/checkout": {
                    "post": {
                        "operationId": "checkout",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["customerId", "amount", "currency"],
                                        "properties": {
                                            "customerId": {"type": "string"},
                                            "amount": {"type": "number"},
                                            "currency": {"type": "string", "enum": ["GBP", "USD", "EUR"]},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {"201": {"description": "Created"}},
                    }
                }
            },
        },
        indent=2,
    )


class CheckoutHandler(BaseHTTPRequestHandler):
    server_version = "PerfAgentUICheckout/0.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._text(200, render_checkout_page(), "text/html; charset=utf-8")
            return
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/openapi.json":
            self._text(200, render_openapi_json(), "application/json")
            return
        if self.path == "/metrics":
            self._text(200, render_metrics(), "text/plain; version=0.0.4")
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        global REQUEST_COUNT, ERROR_COUNT, TOTAL_LATENCY_SECONDS
        started = time.perf_counter()
        REQUEST_COUNT += 1
        if self.path != "/api/checkout":
            ERROR_COUNT += 1
            self._json(404, {"error": "not_found"})
            return
        self._simulate_work()
        try:
            status, body = authorize_checkout(self._read_json())
            if status >= 400:
                ERROR_COUNT += 1
            self._json(status, body)
        finally:
            TOTAL_LATENCY_SECONDS += time.perf_counter() - started

    def log_message(self, format: str, *args: Any) -> None:
        if os.getenv("DEMO_ACCESS_LOG", "0") == "1":
            super().log_message(format, *args)

    def _simulate_work(self) -> None:
        base_ms = float(os.getenv("DEMO_BASE_LATENCY_MS", "30"))
        jitter_ms = float(os.getenv("DEMO_JITTER_MS", "20"))
        time.sleep((base_ms + random.random() * jitter_ms) / 1000)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._text(status, json.dumps(payload), "application/json")

    def _text(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def render_metrics() -> str:
    average_latency = TOTAL_LATENCY_SECONDS / REQUEST_COUNT if REQUEST_COUNT else 0
    return "\n".join(
        [
            "# HELP demo_ui_checkout_requests_total Total checkout requests.",
            "# TYPE demo_ui_checkout_requests_total counter",
            f"demo_ui_checkout_requests_total {REQUEST_COUNT}",
            "# HELP demo_ui_checkout_errors_total Total checkout errors.",
            "# TYPE demo_ui_checkout_errors_total counter",
            f"demo_ui_checkout_errors_total {ERROR_COUNT}",
            "# HELP demo_ui_checkout_duration_seconds_avg Average checkout duration.",
            "# TYPE demo_ui_checkout_duration_seconds_avg gauge",
            f"demo_ui_checkout_duration_seconds_avg {average_latency:.6f}",
            "",
        ]
    )


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), CheckoutHandler)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8083"))
    server = create_server(host, port)
    print(f"ui-checkout-app listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
