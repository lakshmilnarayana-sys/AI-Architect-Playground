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


def authorize_payment(payload: dict[str, Any], payment_number: int) -> tuple[int, dict[str, Any]]:
    missing = [field for field in ["customerId", "amount", "currency"] if field not in payload]
    if missing:
        return 400, {"error": "missing_required_fields", "fields": missing}
    return (
        201,
        {
            "paymentId": f"pay_test_{payment_number}",
            "customerId": payload["customerId"],
            "amount": payload["amount"],
            "currency": payload["currency"],
            "status": "authorized",
        },
    )


class PaymentsHandler(BaseHTTPRequestHandler):
    server_version = "PerfAgentSamplePayments/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/metrics":
            self._metrics()
            return
        if self.path.startswith("/v1/payments/"):
            self._simulate_work()
            payment_id = self.path.rsplit("/", 1)[-1]
            self._json(200, {"paymentId": payment_id, "status": "authorized"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        global REQUEST_COUNT, ERROR_COUNT, TOTAL_LATENCY_SECONDS
        started = time.perf_counter()
        REQUEST_COUNT += 1
        if self.path != "/v1/payments":
            self._json(404, {"error": "not_found"})
            return

        self._simulate_work()
        try:
            payload = self._read_json()
            if random.random() < float(os.getenv("DEMO_ERROR_RATE", "0")):
                ERROR_COUNT += 1
                self._json(503, {"error": "synthetic_overload"})
                return
            status, response = authorize_payment(payload, REQUEST_COUNT)
            if status >= 400:
                ERROR_COUNT += 1
            self._json(status, response)
        finally:
            TOTAL_LATENCY_SECONDS += time.perf_counter() - started

    def log_message(self, format: str, *args: Any) -> None:
        if os.getenv("DEMO_ACCESS_LOG", "0") == "1":
            super().log_message(format, *args)

    def _simulate_work(self) -> None:
        base_ms = float(os.getenv("DEMO_BASE_LATENCY_MS", "20"))
        jitter_ms = float(os.getenv("DEMO_JITTER_MS", "15"))
        time.sleep((base_ms + random.random() * jitter_ms) / 1000)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _metrics(self) -> None:
        average_latency = TOTAL_LATENCY_SECONDS / REQUEST_COUNT if REQUEST_COUNT else 0
        body = "\n".join(
            [
                "# HELP demo_http_requests_total Total HTTP requests handled by the sample service.",
                "# TYPE demo_http_requests_total counter",
                f"demo_http_requests_total {REQUEST_COUNT}",
                "# HELP demo_http_errors_total Total HTTP errors returned by the sample service.",
                "# TYPE demo_http_errors_total counter",
                f"demo_http_errors_total {ERROR_COUNT}",
                "# HELP demo_http_request_duration_seconds_avg Average request duration.",
                "# TYPE demo_http_request_duration_seconds_avg gauge",
                f"demo_http_request_duration_seconds_avg {average_latency:.6f}",
                "",
            ]
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PaymentsHandler)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    server = create_server(host, port)
    print(f"sample-payments-api listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
