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
MAX_RETAINED_LATENCIES = 10000


def run(duration_seconds: int, concurrency: int) -> dict:
    deadline = time.time() + duration_seconds
    request_count = 0
    error_count = 0
    latencies_ms = []
    with grpc.insecure_channel(TARGET) as channel:
        while time.time() < deadline:
            start = time.perf_counter()
            try:
                # TODO: import generated *_pb2_grpc stubs and call SERVICE_FULL_NAME/METHOD_NAME with REQUEST_JSON.
                remaining = max(deadline - time.time(), 0.001)
                grpc.channel_ready_future(channel).result(timeout=min(2, remaining))
            except Exception:
                error_count += 1
            finally:
                if len(latencies_ms) < MAX_RETAINED_LATENCIES:
                    latencies_ms.append((time.perf_counter() - start) * 1000)
                request_count += 1
    return {{"service": SERVICE_NAME, "requests": request_count, "errors": error_count, "latencies_ms": latencies_ms, "concurrency": concurrency}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run(args.duration_seconds, args.concurrency)))
'''
    )
    return output_path
