import importlib.util
def test_sample_payments_api_authorizes_valid_payment():
    spec = importlib.util.spec_from_file_location(
        "sample_payments_api",
        "examples/sample-payments-api/app.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    status, body = module.authorize_payment(
        {"customerId": "cust_test_1001", "amount": 49.99, "currency": "GBP"},
        1,
    )

    assert status == 201
    assert body["status"] == "authorized"
    assert body["amount"] == 49.99


def test_sample_payments_api_rejects_missing_required_fields():
    spec = importlib.util.spec_from_file_location(
        "sample_payments_api",
        "examples/sample-payments-api/app.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    status, body = module.authorize_payment({"customerId": "cust_test_1001"}, 1)

    assert status == 400
    assert body["fields"] == ["amount", "currency"]
