from __future__ import annotations

from pathlib import Path


def generate_websocket_load_test(*, service_name: str, target_url: str, output_path: Path) -> Path:
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


async def worker(duration_seconds: int, worker_id: int) -> dict:
    deadline = time.time() + duration_seconds
    request_count = 0
    error_count = 0
    latencies_ms = []
    async with websockets.connect(TARGET_URL) as websocket:
        while time.time() < deadline:
            payload = {{"type": "ping", "service": SERVICE_NAME, "worker": worker_id, "request": request_count}}
            start = time.perf_counter()
            try:
                await websocket.send(json.dumps(payload))
                await websocket.recv()
            except Exception:
                error_count += 1
            finally:
                latencies_ms.append((time.perf_counter() - start) * 1000)
                request_count += 1
    return {{"requests": request_count, "errors": error_count, "latencies_ms": latencies_ms}}


async def run(duration_seconds: int, connections: int) -> list[dict]:
    return await asyncio.gather(*(worker(duration_seconds, index) for index in range(connections)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--connections", type=int, default=10)
    args = parser.parse_args()
    print(asyncio.run(run(args.duration_seconds, args.connections)))
'''
    )
    return output_path
