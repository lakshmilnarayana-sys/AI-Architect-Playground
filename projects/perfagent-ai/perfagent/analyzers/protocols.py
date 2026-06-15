from __future__ import annotations

import json
from typing import Any


def analyze_protocol_metrics(summary: dict[str, Any], aligned_rows: list[dict[str, Any]]) -> dict[str, Any]:
    protocol_metrics = dict(summary.get("protocol_metrics", {}) or {})
    browser_metrics = dict(summary.get("browser_metrics", {}) or {})
    browser_artifacts = list(summary.get("browser_artifacts", []) or [])
    for row in aligned_rows:
        for key in (
            "grpc_status",
            "grpc_method_latency_ms",
            "grpc_stream_messages",
            "websocket_messages",
            "websocket_message_latency_ms",
            "connection_errors",
            "reconnects",
            "backpressure_events",
        ):
            if key in row and key not in protocol_metrics:
                protocol_metrics[key] = _parse_metric_value(row[key])
        for key, value in row.items():
            if key.startswith("browser_") and key.removeprefix("browser_") not in browser_metrics:
                browser_metrics[key.removeprefix("browser_")] = _parse_metric_value(value)
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
    grpc_method_latency = protocol_metrics.get("grpc_method_latency_ms")
    if isinstance(grpc_method_latency, dict):
        slow_methods = {method: value for method, value in grpc_method_latency.items() if _safe_float(value) > 500}
        if slow_methods:
            findings.append(
                {
                    "type": "grpc_method_latency",
                    "severity": "warn",
                    "evidence": f"gRPC method latency exceeded 500 ms: {slow_methods}",
                    "metric": "grpc_method_latency_ms",
                    "value": slow_methods,
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
    for metric in ("reconnects", "backpressure_events"):
        value = _safe_float(protocol_metrics.get(metric, 0))
        if value > 0:
            findings.append(
                {
                    "type": f"websocket_{metric}",
                    "severity": "warn",
                    "evidence": f"WebSocket {metric.replace('_', ' ')} observed: {value}",
                    "metric": metric,
                    "value": value,
                }
            )
    web_vitals_thresholds = {"lcp_ms": 2500, "inp_ms": 200, "cls": 0.1, "ttfb_ms": 800}
    for metric, threshold in web_vitals_thresholds.items():
        value = _safe_float(browser_metrics.get(metric))
        if value > threshold:
            findings.append(
                {
                    "type": "browser_web_vital",
                    "severity": "warn",
                    "evidence": f"Browser metric {metric}={value} exceeded threshold {threshold}",
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                }
            )
    return {
        "protocol_metrics": protocol_metrics,
        "browser_metrics": browser_metrics,
        "browser_artifacts": browser_artifacts,
        "findings": findings,
        "warnings": [] if protocol_metrics or browser_metrics else ["no protocol-native metrics available"],
    }


def _parse_metric_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
