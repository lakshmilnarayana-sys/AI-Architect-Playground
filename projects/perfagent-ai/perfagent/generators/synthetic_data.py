from __future__ import annotations

import re
from typing import Any


def generate_test_data(contract_analysis: dict[str, Any], seed: int = 1001) -> dict[str, Any]:
    endpoints = []
    for endpoint in contract_analysis.get("endpoints", []):
        endpoints.append(
            {
                "operation_id": endpoint["operation_id"],
                "method": endpoint["method"],
                "path": endpoint["path"],
                "headers": {
                    header: f"test-{_safe_name(header)}-{seed}"
                    for header in endpoint.get("required_headers", [])
                },
                "path_params": {
                    parameter["name"]: _value_for_schema(parameter.get("schema", {}), parameter["name"], seed)
                    for parameter in endpoint.get("path_parameters", [])
                },
                "query": {
                    parameter["name"]: _value_for_schema(parameter.get("schema", {}), parameter["name"], seed)
                    for parameter in endpoint.get("query_parameters", [])
                    if parameter.get("required")
                },
                "body": _value_for_schema(endpoint.get("request_schema", {}), "", seed)
                if endpoint.get("request_schema")
                else None,
            }
        )
    return {"endpoints": endpoints}


def _value_for_schema(schema: dict[str, Any], field_name: str, seed: int) -> Any:
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type", "object" if "properties" in schema else "string")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "string")

    if schema_type == "object":
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        return {
            name: _value_for_schema(child_schema, name, seed)
            for name, child_schema in properties.items()
            if name in required
        }
    if schema_type == "array":
        return [_value_for_schema(schema.get("items", {"type": "string"}), field_name, seed)]
    if schema_type == "integer":
        return seed
    if schema_type == "number":
        return 49.99
    if schema_type == "boolean":
        return True
    return f"test_{_safe_name(field_name or 'value')}_{seed}"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")

