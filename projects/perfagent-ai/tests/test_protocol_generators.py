from perfagent.generators.grpc_generator import generate_grpc_load_test
from perfagent.generators.ui_generator import generate_ui_journey_test
from perfagent.generators.websocket_generator import generate_websocket_load_test
from perfagent.protocols.scenarios import normalize_protocol_scenarios, validate_protocol_scenarios


def test_generate_grpc_load_test_artifact(tmp_path):
    output = tmp_path / "grpc_load.py"

    generate_grpc_load_test(
        service_name="payments-api",
        target="localhost:8082",
        proto_path="./protos/payments.proto",
        output_path=output,
        config={
            "pb2_module": "payments_pb2",
            "pb2_grpc_module": "payments_pb2_grpc",
            "stub_class": "PaymentsStub",
            "method": "CreatePayment",
            "request_class": "CreatePaymentRequest",
            "request": {"customer_id": "cust_1", "amount": 10, "currency": "GBP"},
        },
    )

    content = output.read_text()
    assert "grpc" in content
    assert "grpc.channel_ready_future(channel)" in content
    assert "json.dumps(run(" in content
    assert "MAX_RETAINED_LATENCIES" in content
    assert "PB2_MODULE = 'payments_pb2'" in content
    assert "_build_rpc_client" in content
    assert "rpc(request_type(**REQUEST_JSON)" in content
    assert "grpc_status" in content
    assert "grpc.RpcError" in content
    assert "payments-api" in content
    assert "localhost:8082" in content


def test_generate_websocket_load_test_artifact(tmp_path):
    output = tmp_path / "websocket_load.py"

    generate_websocket_load_test(
        service_name="payments-api",
        target_url="ws://localhost:8081/ws",
        output_path=output,
        config={
            "sequence": [
                {
                    "message": {"type": "authorizePayment", "customerId": "cust_ws_1"},
                    "expect_json_field": "status",
                    "think_time_ms": 10,
                }
            ]
        },
    )

    content = output.read_text()
    assert "websockets" in content
    assert "json.dumps(asyncio.run(" in content
    assert "MAX_RETAINED_LATENCIES" in content
    assert "MESSAGE_SEQUENCE" in content
    assert "expect_json_field" in content
    assert "think_time_ms" in content
    assert "websocket_messages" in content
    assert "connection_errors" in content
    assert "payments-api" in content
    assert "ws://localhost:8081/ws" in content


def test_protocol_scenario_config_normalizes_and_validates_all_protocols():
    config = {
        "grpc": {
            "proto_path": "./protos/payments.proto",
            "pb2_module": "payments_pb2",
            "pb2_grpc_module": "payments_pb2_grpc",
            "stub_class": "PaymentsStub",
            "method": "CreatePayment",
            "request_class": "CreatePaymentRequest",
            "request": {"customer_id": "cust_1", "amount": 10, "currency": "GBP"},
        },
        "websocket": {
            "target_url": "ws://localhost:8081/ws",
            "scenarios": [
                {
                    "name": "authorize-payment",
                    "sequence": [{"send": {"type": "authorizePayment"}, "expect": {"json_field": "status"}}],
                }
            ],
        },
        "ui": {
            "journeys": [
                {
                    "name": "checkout",
                    "path": "/checkout",
                    "steps": [
                        {"action": "goto", "path": "/checkout"},
                        {"action": "click", "selector": "button[type=submit]"},
                    ],
                    "web_vitals": True,
                    "screenshot_on_error": True,
                }
            ]
        },
    }

    normalized = normalize_protocol_scenarios(config)
    validation = validate_protocol_scenarios(normalized)

    assert validation["valid"] is True
    assert normalized["grpc"]["scenario_name"] == "CreatePayment"
    assert normalized["websocket"]["sequence"][0]["message"] == {"type": "authorizePayment"}
    assert normalized["websocket"]["sequence"][0]["expect_json_field"] == "status"
    assert normalized["ui"]["journey_name"] == "checkout"
    assert normalized["ui"]["steps"][1]["selector"] == "button[type=submit]"
    assert normalized["ui"]["web_vitals"] is True
    assert normalized["ui"]["screenshot_on_error"] is True


def test_ui_generator_uses_journey_steps_and_error_screenshot(tmp_path):
    output = tmp_path / "ui_journey.py"

    generate_ui_journey_test(
        service_name="checkout-ui",
        target_url="http://localhost:8083",
        output_path=output,
        config={
            "journey_name": "checkout",
            "steps": [
                {"action": "goto", "path": "/checkout"},
                {"action": "fill", "selector": "#amount", "value": "49.99"},
                {"action": "click", "selector": "button[type=submit]"},
                {"action": "wait_for_selector", "selector": ".receipt"},
            ],
            "screenshot_on_error": True,
            "web_vitals": True,
        },
    )

    content = output.read_text()
    assert "JOURNEY_NAME = 'checkout'" in content
    assert "JOURNEY_STEPS" in content
    assert "page.fill" in content
    assert "page.screenshot" in content
    assert "largest_contentful_paint_ms" in content
