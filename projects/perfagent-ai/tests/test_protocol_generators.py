from perfagent.generators.grpc_generator import generate_grpc_load_test
from perfagent.generators.websocket_generator import generate_websocket_load_test


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
    assert "payments-api" in content
    assert "ws://localhost:8081/ws" in content
