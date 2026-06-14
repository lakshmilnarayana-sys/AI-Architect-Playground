from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_websocket_load_test(
    *,
    service_name: str,
    target_url: str,
    output_path: Path,
    config: dict[str, Any] | None = None,
) -> Path:
    config = config or {}
    message = config.get("message", {"type": "ping"})
    sequence = config.get("sequence") or [{"message": message, "think_time_ms": 0}]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f'''"""Generated WebSocket load harness for {service_name}."""

import argparse
import asyncio
import json
import time

import websockets


SERVICE_NAME = {service_name!r}
TARGET_URL = {target_url!r}
MESSAGE_TEMPLATE = {message!r}
MESSAGE_SEQUENCE = {sequence!r}
MAX_RETAINED_LATENCIES = 10000


async def worker(duration_seconds: int, worker_id: int) -> dict:
    deadline = time.time() + duration_seconds
    request_count = 0
    error_count = 0
    latencies_ms = []
    try:
        async with websockets.connect(TARGET_URL) as websocket:
            while time.time() < deadline:
                for step in MESSAGE_SEQUENCE:
                    if time.time() >= deadline:
                        break
                    payload = dict(step.get("message", MESSAGE_TEMPLATE))
                    payload.update({{"service": SERVICE_NAME, "worker": worker_id, "request": request_count}})
                    start = time.perf_counter()
                    try:
                        await websocket.send(json.dumps(payload))
                        response = await websocket.recv()
                        expect_field = step.get("expect_json_field")
                        if expect_field:
                            parsed = json.loads(response)
                            if expect_field not in parsed:
                                error_count += 1
                    except Exception:
                        error_count += 1
                    finally:
                        if len(latencies_ms) < MAX_RETAINED_LATENCIES:
                            latencies_ms.append((time.perf_counter() - start) * 1000)
                        request_count += 1
                    think_time_ms = int(step.get("think_time_ms", 0) or 0)
                    if think_time_ms:
                        await asyncio.sleep(think_time_ms / 1000)
    except Exception:
        start = time.perf_counter()
        error_count += 1
        request_count += 1
        latencies_ms.append((time.perf_counter() - start) * 1000)
    return {{"requests": request_count, "errors": error_count, "latencies_ms": latencies_ms}}


async def run(duration_seconds: int, connections: int) -> list[dict]:
    return await asyncio.gather(*(worker(duration_seconds, index) for index in range(connections)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--connections", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.duration_seconds, args.connections))))
'''
    )
    return output_path
