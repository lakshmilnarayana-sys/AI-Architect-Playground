from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_grpc_load_test(
    *,
    service_name: str,
    target: str,
    proto_path: str,
    output_path: Path,
    config: dict[str, Any] | None = None,
) -> Path:
    config = config or {}
    service_full_name = config.get("service_full_name", "payments.Payments")
    method_name = config.get("method", "CreatePayment")
    request_json = config.get("request", {})
    pb2_module = config.get("pb2_module")
    pb2_grpc_module = config.get("pb2_grpc_module")
    stub_class = config.get("stub_class")
    request_class = config.get("request_class")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f'''"""Generated gRPC load harness for {service_name}.

This is a first-class PerfAgent protocol artifact. Fill in the generated stub import and RPC method for your service.
"""

import argparse
import json
import time

import grpc


SERVICE_NAME = {service_name!r}
TARGET = {target!r}
PROTO_PATH = {proto_path!r}
SERVICE_FULL_NAME = {service_full_name!r}
METHOD_NAME = {method_name!r}
REQUEST_JSON = {request_json!r}
PB2_MODULE = {pb2_module!r}
PB2_GRPC_MODULE = {pb2_grpc_module!r}
STUB_CLASS = {stub_class!r}
REQUEST_CLASS = {request_class!r}
MAX_RETAINED_LATENCIES = 10000


def _build_rpc_client(channel):
    if not (PB2_MODULE and PB2_GRPC_MODULE and STUB_CLASS and REQUEST_CLASS):
        return None
    import importlib

    pb2 = importlib.import_module(PB2_MODULE)
    pb2_grpc = importlib.import_module(PB2_GRPC_MODULE)
    stub = getattr(pb2_grpc, STUB_CLASS)(channel)
    request_type = getattr(pb2, REQUEST_CLASS)
    rpc = getattr(stub, METHOD_NAME)
    return rpc, request_type


def run(duration_seconds: int, concurrency: int) -> dict:
    deadline = time.time() + duration_seconds
    request_count = 0
    error_count = 0
    latencies_ms = []
    grpc_status = {{}}
    with grpc.insecure_channel(TARGET) as channel:
        rpc_client = _build_rpc_client(channel)
        while time.time() < deadline:
            start = time.perf_counter()
            try:
                remaining = max(deadline - time.time(), 0.001)
                if rpc_client:
                    rpc, request_type = rpc_client
                    rpc(request_type(**REQUEST_JSON), timeout=min(2, remaining))
                else:
                    grpc.channel_ready_future(channel).result(timeout=min(2, remaining))
                status = "OK"
            except grpc.RpcError as exc:
                code = exc.code()
                status = getattr(code, "name", str(code))
                error_count += 1
            except Exception:
                status = "EXCEPTION"
                error_count += 1
            finally:
                grpc_status[status] = grpc_status.get(status, 0) + 1
                if len(latencies_ms) < MAX_RETAINED_LATENCIES:
                    latencies_ms.append((time.perf_counter() - start) * 1000)
                request_count += 1
    return {{
        "service": SERVICE_NAME,
        "requests": request_count,
        "errors": error_count,
        "latencies_ms": latencies_ms,
        "concurrency": concurrency,
        "grpc_status": grpc_status,
        "protocol_metrics": {{"grpc_status": grpc_status}},
    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run(args.duration_seconds, args.concurrency)))
'''
    )
    return output_path
