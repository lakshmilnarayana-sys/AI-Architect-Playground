from __future__ import annotations

import json
from typing import Any


def analyze_protocol_metrics(summary: dict[str, Any], aligned_rows: list[dict[str, Any]]) -> dict[str, Any]:
    protocol_metrics = dict(summary.get("protocol_metrics", {}) or {})
    for row in aligned_rows:
        for key in ("grpc_status", "websocket_messages", "connection_errors"):
            if key in row and key not in protocol_metrics:
                protocol_metrics[key] = _parse_metric_value(row[key])
    findings: list[dict[str, Any]] = []
    grpc_status = protocol_metrics.get("grpc_status")
    if isinstance(grpc_status, dict):
        non_ok = {status: count for status, count in grpc_status.items() if status != "OK" and float(count or 0) > 0}
        if non_ok:
            findings.append(
                {
                    "type": "grpc_status_errors",
                    "severity": "warn",
                    "evidence": f"gRPC non-OK statuses observed: {non_ok}",
                    "metric": "grpc_status",
                    "value": non_ok,
                }
            )
    connection_errors = float(protocol_metrics.get("connection_errors", 0) or 0)
    if connection_errors > 0:
        findings.append(
            {
                "type": "websocket_connection_errors",
                "severity": "warn",
                "evidence": f"WebSocket connection errors observed: {connection_errors}",
                "metric": "connection_errors",
                "value": connection_errors,
            }
        )
    return {
        "protocol_metrics": protocol_metrics,
        "findings": findings,
        "warnings": [] if protocol_metrics else ["no protocol-native metrics available"],
    }


def _parse_metric_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value
