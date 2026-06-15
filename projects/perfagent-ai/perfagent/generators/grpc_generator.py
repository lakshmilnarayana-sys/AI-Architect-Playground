from __future__ import annotations

from pathlib import Path
import re
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
    proto = Path(proto_path)
    proto_text = proto.read_text() if proto.exists() else ""
    auto_compile = bool(config.get("auto_compile", config.get("compile_proto", False)))
    service_full_name = config.get("service_full_name", "payments.Payments")
    method_name = config.get("method", "CreatePayment")
    request_json = config.get("request", {})
    inferred = _infer_proto_symbols(proto, proto_text, method_name)
    pb2_module = config.get("pb2_module") or (inferred["pb2_module"] if auto_compile else None)
    pb2_grpc_module = config.get("pb2_grpc_module") or (inferred["pb2_grpc_module"] if auto_compile else None)
    stub_class = config.get("stub_class") or (inferred["stub_class"] if auto_compile else None)
    request_class = config.get("request_class") or (inferred["request_class"] if auto_compile else None)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f'''"""Generated gRPC load harness for {service_name}.

This is a first-class PerfAgent protocol artifact. Fill in the generated stub import and RPC method for your service.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import grpc


SERVICE_NAME = {service_name!r}
TARGET = {target!r}
PROTO_PATH = {proto_path!r}
SERVICE_FULL_NAME = {service_full_name!r}
METHOD_NAME = {method_name!r}
REQUEST_JSON = {request_json!r}
AUTO_COMPILE_PROTO = {auto_compile!r}
GENERATED_PROTO_DIR = str(Path(__file__).resolve().parent / "_generated_proto")
PB2_MODULE = {pb2_module!r}
PB2_GRPC_MODULE = {pb2_grpc_module!r}
STUB_CLASS = {stub_class!r}
REQUEST_CLASS = {request_class!r}
MAX_RETAINED_LATENCIES = 10000


def _ensure_generated_stubs():
    if not AUTO_COMPILE_PROTO:
        return
    generated = Path(GENERATED_PROTO_DIR)
    generated.mkdir(parents=True, exist_ok=True)
    if GENERATED_PROTO_DIR not in sys.path:
        sys.path.insert(0, GENERATED_PROTO_DIR)
    try:
        from grpc_tools import protoc
    except Exception as exc:
        raise RuntimeError("grpc_tools is required for auto_compile gRPC scenarios") from exc
    proto = Path(PROTO_PATH).resolve()
    exit_code = protoc.main([
        "grpc_tools.protoc",
        f"-I{{proto.parent}}",
        f"--python_out={{generated}}",
        f"--grpc_python_out={{generated}}",
        str(proto),
    ])
    if exit_code:
        raise RuntimeError(f"grpc_tools.protoc failed with exit code {{exit_code}} for {{proto}}")


def _build_rpc_client(channel):
    _ensure_generated_stubs()
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


def _infer_proto_symbols(proto_path: Path, proto_text: str, method_name: str) -> dict[str, str | None]:
    module_base = proto_path.stem
    service_match = re.search(r"\bservice\s+(\w+)\s*{", proto_text)
    rpc_match = re.search(rf"\brpc\s+{re.escape(method_name)}\s*\(\s*(\w+)\s*\)", proto_text)
    return {
        "pb2_module": f"{module_base}_pb2",
        "pb2_grpc_module": f"{module_base}_pb2_grpc",
        "stub_class": f"{service_match.group(1)}Stub" if service_match else None,
        "request_class": rpc_match.group(1) if rpc_match else None,
    }
