from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def parse_openapi(path: Path, service_name: str) -> dict[str, Any]:
    spec = _load_spec(path)
    endpoints: list[dict[str, Any]] = []

    for route, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            parameters = _merge_parameters(path_item.get("parameters", []), operation.get("parameters", []))
            request_schema = _request_schema(operation)
            endpoint = {
                "method": method.upper(),
                "path": route,
                "operation_id": operation.get("operationId") or _operation_id(method, route),
                "requires_body": bool(operation.get("requestBody", {}).get("required") or request_schema),
                "criticality": _criticality(method, route),
                "test_priority": 1 if method.lower() in {"post", "get"} else 2,
                "required_headers": [
                    parameter["name"]
                    for parameter in parameters
                    if parameter.get("in") == "header" and parameter.get("required")
                ],
                "path_parameters": _parameters_by_location(parameters, "path", include_required=False),
                "query_parameters": _parameters_by_location(parameters, "query", include_required=True),
                "request_schema": request_schema,
                "response_schemas": _response_schemas(operation),
                "expected_status": _expected_status(operation),
                "auth_required": bool(operation.get("security") or spec.get("security")),
            }
            endpoints.append(endpoint)

    return {"service_name": service_name, "endpoints": endpoints}


def _load_spec(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _merge_parameters(path_parameters: Any, operation_parameters: Any) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for parameter in [*list(path_parameters or []), *list(operation_parameters or [])]:
        if isinstance(parameter, dict) and "$ref" not in parameter:
            parameters.append(parameter)
    return parameters


def _parameters_by_location(
    parameters: list[dict[str, Any]], location: str, *, include_required: bool
) -> list[dict[str, Any]]:
    extracted = []
    for parameter in parameters:
        if parameter.get("in") != location:
            continue
        item = {"name": parameter["name"], "schema": parameter.get("schema", {"type": "string"})}
        if include_required:
            item["required"] = bool(parameter.get("required"))
        extracted.append(item)
    return extracted


def _request_schema(operation: dict[str, Any]) -> dict[str, Any]:
    request_body = operation.get("requestBody") or {}
    content = request_body.get("content") or {}
    json_content = content.get("application/json") or next(iter(content.values()), {})
    return json_content.get("schema") or {}


def _response_schemas(operation: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for status, response in (operation.get("responses") or {}).items():
        content = response.get("content") or {}
        if "application/json" in content:
            schemas[status] = content["application/json"].get("schema", {})
    return schemas


def _expected_status(operation: dict[str, Any]) -> int:
    for status in (operation.get("responses") or {}).keys():
        if str(status).isdigit() and 200 <= int(status) < 400:
            return int(status)
    return 200


def _operation_id(method: str, route: str) -> str:
    parts = [part for part in route.replace("{", "").replace("}", "").split("/") if part]
    return f"{method.lower()}_" + "_".join(parts)


def _criticality(method: str, route: str) -> str:
    if method.lower() in {"post", "put", "patch", "delete"}:
        return "high"
    if any(token in route.lower() for token in ["payment", "checkout", "order"]):
        return "high"
    return "medium"

