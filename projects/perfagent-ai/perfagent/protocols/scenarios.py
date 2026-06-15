from __future__ import annotations

from typing import Any


def normalize_protocol_scenarios(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    return {
        "grpc": _normalize_grpc(config.get("grpc", {}) or {}),
        "websocket": _normalize_websocket(config.get("websocket", {}) or {}),
        "ui": _normalize_ui(config.get("ui", {}) or {}),
    }


def validate_protocol_scenarios(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_protocol_scenarios(config)
    errors: list[str] = []
    warnings: list[str] = []

    grpc = normalized["grpc"]
    if grpc.get("enabled", True):
        for key in ["proto_path", "method"]:
            if not grpc.get(key):
                errors.append(f"grpc.{key} is required")
        stub_keys = ["pb2_module", "pb2_grpc_module", "stub_class", "request_class"]
        missing_stub_keys = [key for key in stub_keys if not grpc.get(key)]
        if missing_stub_keys:
            warnings.append("grpc stub invocation will fall back to channel readiness; missing " + ", ".join(missing_stub_keys))

    websocket = normalized["websocket"]
    if websocket.get("enabled", True) and not websocket.get("sequence"):
        errors.append("websocket.sequence must contain at least one message step")

    ui = normalized["ui"]
    if ui.get("enabled", True) and not ui.get("steps"):
        errors.append("ui.steps must contain at least one browser step")

    return {"valid": not errors, "errors": errors, "warnings": warnings, "normalized": normalized}


def _normalize_grpc(config: dict[str, Any]) -> dict[str, Any]:
    method = config.get("method", "CreatePayment")
    scenario = dict(config)
    scenario.setdefault("enabled", True)
    scenario.setdefault("proto_path", "./protos/service.proto")
    scenario.setdefault("service_full_name", "payments.Payments")
    scenario.setdefault("method", method)
    scenario.setdefault("scenario_name", method)
    scenario.setdefault("request", {})
    return scenario


def _normalize_websocket(config: dict[str, Any]) -> dict[str, Any]:
    scenario = _first_named(config, "scenarios")
    message = config.get("message", scenario.get("message", {"type": "ping"}))
    raw_sequence = scenario.get("sequence") or config.get("sequence") or [{"message": message, "think_time_ms": 0}]
    sequence = [_normalize_websocket_step(step, message) for step in raw_sequence]
    return {
        **config,
        **scenario,
        "enabled": config.get("enabled", scenario.get("enabled", True)),
        "scenario_name": scenario.get("name", config.get("scenario_name", "default-websocket")),
        "message": message,
        "sequence": sequence,
    }


def _normalize_websocket_step(step: dict[str, Any], default_message: dict[str, Any]) -> dict[str, Any]:
    message = step.get("message", step.get("send", default_message))
    normalized = {"message": message, "think_time_ms": int(step.get("think_time_ms", 0) or 0)}
    expect = step.get("expect", {}) or {}
    if step.get("expect_json_field"):
        normalized["expect_json_field"] = step["expect_json_field"]
    elif expect.get("json_field"):
        normalized["expect_json_field"] = expect["json_field"]
    if expect.get("json_equals"):
        normalized["expect_json_equals"] = expect["json_equals"]
    return normalized


def _normalize_ui(config: dict[str, Any]) -> dict[str, Any]:
    journey = _first_named(config, "journeys")
    path = journey.get("path", config.get("path", "/"))
    steps = journey.get("steps") or config.get("steps") or [{"action": "goto", "path": path}]
    return {
        **config,
        **journey,
        "enabled": config.get("enabled", journey.get("enabled", True)),
        "journey_name": journey.get("name", config.get("journey_name", "default-ui")),
        "path": path,
        "steps": steps,
        "web_vitals": bool(journey.get("web_vitals", config.get("web_vitals", True))),
        "screenshot_on_error": bool(journey.get("screenshot_on_error", config.get("screenshot_on_error", False))),
    }


def _first_named(config: dict[str, Any], key: str) -> dict[str, Any]:
    values = config.get(key)
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return dict(values[0])
    return {}
