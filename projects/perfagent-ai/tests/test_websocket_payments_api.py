from __future__ import annotations

import importlib.util
import json


def test_websocket_payment_message_authorizes_valid_payload(monkeypatch):
    monkeypatch.setenv("DEMO_BASE_LATENCY_MS", "0")
    monkeypatch.setenv("DEMO_JITTER_MS", "0")
    module = _load_module()

    response = module.authorize_payment_message(
        json.dumps({"customerId": "cust_ws_1001", "amount": 49.99, "currency": "GBP"}),
        started=100.0,
        ended=100.025,
    )

    payload = json.loads(response)
    assert payload["type"] == "payment.authorized"
    assert payload["paymentId"] == "pay_ws_100000"
    assert payload["customerId"] == "cust_ws_1001"
    assert payload["amount"] == 49.99
    assert payload["currency"] == "GBP"
    assert payload["durationMs"] == 25.0


def test_websocket_payment_message_rejects_missing_required_fields():
    module = _load_module()

    response = module.authorize_payment_message(
        json.dumps({"customerId": "cust_ws_1001"}),
        started=100.0,
        ended=100.001,
    )

    payload = json.loads(response)
    assert payload["type"] == "payment.rejected"
    assert payload["reason"] == "missing_required_fields"
    assert payload["fields"] == ["amount", "currency"]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "websocket_payments_api",
        "examples/demo-apps/websocket-payments-api/app.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
