from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any

import websockets


async def handler(websocket: Any) -> None:
    async for message in websocket:
        started = time.perf_counter()
        await asyncio.sleep(_latency_seconds())
        await websocket.send(authorize_payment_message(message, started=started, ended=time.perf_counter()))


def authorize_payment_message(message: str, *, started: float, ended: float) -> str:
    payload = json.loads(message)
    missing = [field for field in ["amount", "currency"] if field not in payload]
    if not payload.get("customerId"):
        missing.insert(0, "customerId")
    if missing:
        return json.dumps(
            {
                "type": "payment.rejected",
                "reason": "missing_required_fields",
                "fields": missing,
                "durationMs": round((ended - started) * 1000, 2),
            }
        )
    response = {
        "type": "payment.authorized",
        "paymentId": f"pay_ws_{int(started * 1000)}",
        "customerId": payload["customerId"],
        "amount": payload["amount"],
        "currency": payload["currency"],
        "durationMs": round((ended - started) * 1000, 2),
    }
    return json.dumps(response)


def _latency_seconds() -> float:
    base_ms = float(os.getenv("DEMO_BASE_LATENCY_MS", "10"))
    jitter_ms = float(os.getenv("DEMO_JITTER_MS", "10"))
    return (base_ms + random.random() * jitter_ms) / 1000


async def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8081"))
    async with websockets.serve(handler, host, port):
        print(f"websocket-payments-api listening on {host}:{port}", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
