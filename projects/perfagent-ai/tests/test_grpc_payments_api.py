from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from grpc_tools import protoc


APP_DIR = Path("examples/demo-apps/grpc-payments-api")
PROTO_PATH = APP_DIR / "protos" / "payments.proto"


def test_grpc_proto_defines_payments_create_payment_rpc():
    proto = PROTO_PATH.read_text()

    assert "service Payments" in proto
    assert "rpc CreatePayment (CreatePaymentRequest) returns (CreatePaymentResponse);" in proto
    assert "string customer_id = 1;" in proto
    assert "double amount = 2;" in proto
    assert "string currency = 3;" in proto


def test_grpc_payments_service_authorizes_payment(tmp_path, monkeypatch):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    exit_code = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{PROTO_PATH.parent}",
            f"--python_out={generated_dir}",
            f"--grpc_python_out={generated_dir}",
            str(PROTO_PATH),
        ]
    )
    assert exit_code == 0

    monkeypatch.syspath_prepend(str(generated_dir))
    monkeypatch.setenv("DEMO_BASE_LATENCY_MS", "0")
    monkeypatch.setenv("DEMO_JITTER_MS", "0")

    server_module = _load_server_module()
    payments_pb2 = sys.modules["payments_pb2"]

    response = server_module.PaymentsService().CreatePayment(
        payments_pb2.CreatePaymentRequest(
            customer_id="cust_test_1001",
            amount=49.99,
            currency="GBP",
        ),
        context=None,
    )

    assert response.payment_id.startswith("pay_grpc_")
    assert response.status == "authorized"


def test_grpc_payments_service_rejects_missing_required_fields(tmp_path, monkeypatch):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    exit_code = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{PROTO_PATH.parent}",
            f"--python_out={generated_dir}",
            f"--grpc_python_out={generated_dir}",
            str(PROTO_PATH),
        ]
    )
    assert exit_code == 0

    monkeypatch.syspath_prepend(str(generated_dir))
    monkeypatch.setenv("DEMO_BASE_LATENCY_MS", "0")
    monkeypatch.setenv("DEMO_JITTER_MS", "0")

    server_module = _load_server_module()
    payments_pb2 = sys.modules["payments_pb2"]

    response = server_module.PaymentsService().CreatePayment(
        payments_pb2.CreatePaymentRequest(customer_id="", amount=0, currency=""),
        context=None,
    )

    assert response.payment_id == ""
    assert response.status == "rejected_missing_required_fields"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("grpc_payments_server", APP_DIR / "server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
