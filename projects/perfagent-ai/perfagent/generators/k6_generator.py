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
    endpoint_mix = _endpoint_mix_for_test_data(strategy.get("endpoint_mix", []), test_data.get("endpoints", []))
    p95 = thresholds.get("p95_latency_ms", 500)
    error_rate = float(thresholds.get("error_rate_percent", 1)) / 100

    lines = [
        "import http from 'k6/http';",
        "import { check, sleep } from 'k6';",
        "",
        f"const BASE_URL = {json.dumps(target_url.rstrip('/'))};",
        f"const ENDPOINT_MIX = {json.dumps(endpoint_mix)};",
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
    if endpoint_mix:
        lines.extend(
            [
                "  const draw = Math.random();",
                "  const selected = ENDPOINT_MIX.find((item) => draw <= item.cumulative) || ENDPOINT_MIX[ENDPOINT_MIX.length - 1];",
            ]
        )

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

        prefix = "  " if not endpoint_mix else f"  if (selected.operation_id === {json.dumps(operation_id)}) {{ "
        suffix = "" if not endpoint_mix else " }"
        if method in {"post", "put", "patch"}:
            lines.append(
                f"{prefix}{_response_assignment(index)} http.{method}(`${{BASE_URL}}{path}`, {json.dumps(json.dumps(body or {}))}, {json.dumps(params)});{suffix}"
            )
        else:
            lines.append(f"{prefix}{_response_assignment(index)} http.{method}(`${{BASE_URL}}{path}`, {json.dumps(params)});{suffix}")
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


def _endpoint_mix_for_test_data(endpoint_mix: list[dict[str, Any]], endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not endpoint_mix:
        return []
    weights_by_path = {item.get("path"): float(item.get("weight", 0) or 0) for item in endpoint_mix}
    selected = []
    cumulative = 0.0
    for endpoint in endpoints:
        weight = weights_by_path.get(endpoint.get("path"), 0.0)
        if weight <= 0:
            continue
        cumulative += weight
        selected.append({"operation_id": endpoint["operation_id"], "path": endpoint["path"], "cumulative": cumulative})
    if selected and selected[-1]["cumulative"] != 1:
        scale = selected[-1]["cumulative"]
        selected = [{**item, "cumulative": item["cumulative"] / scale} for item in selected]
    return selected
