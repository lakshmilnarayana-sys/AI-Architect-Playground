from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_k6_script(
    contract_analysis: dict[str, Any],
    test_data: dict[str, Any],
    strategy: dict[str, Any],
    target_url: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    endpoint_status = {
        endpoint["operation_id"]: endpoint.get("expected_status", 200)
        for endpoint in contract_analysis.get("endpoints", [])
    }
    stages = strategy.get("stages", [{"duration": "1m", "target": 10}])
    thresholds = strategy.get("thresholds", {})
    p95 = thresholds.get("p95_latency_ms", 500)
    error_rate = float(thresholds.get("error_rate_percent", 1)) / 100

    lines = [
        "import http from 'k6/http';",
        "import { check, sleep } from 'k6';",
        "",
        f"const BASE_URL = {json.dumps(target_url.rstrip('/'))};",
        "",
        "export const options = {",
        f"  stages: {json.dumps(stages)},",
        "  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],",
        "  thresholds: {",
        f"    http_req_duration: ['p(95)<{p95}'],",
        f"    http_req_failed: ['rate<{error_rate:g}'],",
        "  },",
        "};",
        "",
        "export default function () {",
    ]

    for index, item in enumerate(test_data.get("endpoints", [])):
        method = item["method"].lower()
        operation_id = item["operation_id"]
        path = _apply_path_params(item["path"], item.get("path_params", {}))
        if item.get("query"):
            path = f"{path}?{_query_string(item['query'])}"
        headers = {"Content-Type": "application/json", **item.get("headers", {})}
        params = {"headers": headers}
        expected_status = endpoint_status.get(operation_id, 200)
        body = item.get("body")

        if method in {"post", "put", "patch"}:
            lines.append(
                f"  {_response_assignment(index)} http.{method}(`${{BASE_URL}}{path}`, {json.dumps(json.dumps(body or {}))}, {json.dumps(params)});"
            )
        else:
            lines.append(f"  {_response_assignment(index)} http.{method}(`${{BASE_URL}}{path}`, {json.dumps(params)});")
        lines.append(
            f"  check(res, {{ '{operation_id} status is {expected_status}': (r) => r.status === {expected_status} }});"
        )
    lines.extend(["  sleep(1);", "}"])
    output_path.write_text("\n".join(lines) + "\n")
    return output_path


def _apply_path_params(path: str, params: dict[str, Any]) -> str:
    for name, value in params.items():
        path = path.replace("{" + name + "}", str(value))
    return path


def _query_string(params: dict[str, Any]) -> str:
    return "&".join(f"{name}={str(value).lower() if isinstance(value, bool) else value}" for name, value in params.items())


def _response_assignment(index: int) -> str:
    return "let res =" if index == 0 else "res ="
