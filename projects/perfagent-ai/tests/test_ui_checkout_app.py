from __future__ import annotations

import importlib.util
import json


def test_ui_checkout_page_contains_perf_test_controls():
    module = _load_module()

    html = module.render_checkout_page()

    assert "PerfAgent Checkout" in html
    assert 'id="checkout-form"' in html
    assert 'data-perf-target="checkout-submit"' in html
    assert "fetch('/api/checkout'" in html
    assert "PerformanceObserver" in html


def test_ui_checkout_api_authorizes_valid_request():
    module = _load_module()

    status, body = module.authorize_checkout(
        {"customerId": "cust_ui_1001", "amount": 49.99, "currency": "GBP"}
    )

    assert status == 201
    assert body["status"] == "authorized"
    assert body["channel"] == "ui"


def test_ui_checkout_api_rejects_missing_fields():
    module = _load_module()

    status, body = module.authorize_checkout({"customerId": "cust_ui_1001"})

    assert status == 400
    assert body == {"error": "missing_required_fields", "fields": ["amount", "currency"]}


def test_ui_checkout_openapi_describes_checkout_endpoint():
    spec = json.loads(_load_module().render_openapi_json())

    assert spec["paths"]["/api/checkout"]["post"]["operationId"] == "checkout"
    required = spec["paths"]["/api/checkout"]["post"]["requestBody"]["content"]["application/json"]["schema"]["required"]
    assert required == ["customerId", "amount", "currency"]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "ui_checkout_app",
        "examples/demo-apps/ui-checkout-app/app.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
