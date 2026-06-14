from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def generate_locustfile(
    contract_analysis: dict[str, Any],
    test_data: dict[str, Any],
    target_url: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "from locust import HttpUser, between, task",
        "",
        "",
        "class PerfAgentUser(HttpUser):",
        f"    host = {json.dumps(target_url.rstrip('/'))}",
        "    wait_time = between(0.1, 1.0)",
        "",
    ]
    for item in test_data.get("endpoints", []):
        method = item["method"].lower()
        function_name = _safe_identifier(item["operation_id"])
        path = _apply_path_params(item["path"], item.get("path_params", {}))
        headers = item.get("headers", {})
        body = item.get("body")
        lines.extend(
            [
                "    @task",
                f"    def {function_name}(self):",
            ]
        )
        if method in {"post", "put", "patch"}:
            lines.append(
                f"        self.client.{method}({json.dumps(path)}, json={json.dumps(body or {})}, headers={json.dumps(headers)}, name={json.dumps(item['operation_id'])})"
            )
        else:
            lines.append(
                f"        self.client.{method}({json.dumps(path)}, headers={json.dumps(headers)}, name={json.dumps(item['operation_id'])})"
            )
        lines.append("")
    output_path.write_text("\n".join(lines))
    return output_path


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if normalized and normalized[0].isdigit():
        normalized = f"op_{normalized}"
    return normalized or "endpoint"


def _apply_path_params(path: str, params: dict[str, Any]) -> str:
    for name, value in params.items():
        path = path.replace("{" + name + "}", str(value))
    return path
