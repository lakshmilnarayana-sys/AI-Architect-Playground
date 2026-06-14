from pathlib import Path

from perfagent.parsers.openapi_parser import parse_openapi


def test_parse_openapi_extracts_endpoints_and_required_fields():
    analysis = parse_openapi(Path("examples/sample-openapi.yaml"), "payments-api")

    assert analysis["service_name"] == "payments-api"
    assert len(analysis["endpoints"]) == 2

    create_payment = analysis["endpoints"][0]
    assert create_payment["method"] == "POST"
    assert create_payment["path"] == "/v1/payments"
    assert create_payment["operation_id"] == "createPayment"
    assert create_payment["requires_body"] is True
    assert create_payment["required_headers"] == ["x-request-id"]
    assert create_payment["request_schema"]["required"] == [
        "customerId",
        "amount",
        "currency",
    ]

    get_payment = analysis["endpoints"][1]
    assert get_payment["path_parameters"] == [{"name": "paymentId", "schema": {"type": "string"}}]
    assert get_payment["query_parameters"] == [
        {"name": "includeEvents", "required": False, "schema": {"type": "boolean"}}
    ]
