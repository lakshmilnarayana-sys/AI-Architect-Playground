from perfagent.generators.grpc_generator import generate_grpc_load_test
from perfagent.generators.websocket_generator import generate_websocket_load_test


def test_generate_grpc_load_test_artifact(tmp_path):
    output = tmp_path / "grpc_load.py"

    generate_grpc_load_test(
        service_name="payments-api",
        target="localhost:8082",
        proto_path="./protos/payments.proto",
        output_path=output,
    )

    content = output.read_text()
    assert "grpc" in content
    assert "payments-api" in content
    assert "localhost:8082" in content


def test_generate_websocket_load_test_artifact(tmp_path):
    output = tmp_path / "websocket_load.py"

    generate_websocket_load_test(
        service_name="payments-api",
        target_url="ws://localhost:8081/ws",
        output_path=output,
    )

    content = output.read_text()
    assert "websockets" in content
    assert "payments-api" in content
    assert "ws://localhost:8081/ws" in content
