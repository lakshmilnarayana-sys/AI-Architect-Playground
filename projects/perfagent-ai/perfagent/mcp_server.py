from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from perfagent.core.artifacts import read_json
from perfagent.storage.run_store import RunStore, compare_to_latest_baseline
from perfagent.workflow import evaluate_service


TOOLS = [
    {
        "name": "analyze_run",
        "description": "Read a PerfAgent run summary and return release decision, features, and bottleneck analysis.",
    },
    {
        "name": "list_runs",
        "description": "List stored PerfAgent runs from the SQLite run store.",
    },
    {
        "name": "compare_regression",
        "description": "Compare a run summary against the latest stored baseline for the same service.",
    },
    {
        "name": "evaluate_service",
        "description": "Run PerfAgent evaluation for a service and return report paths, features, and decision.",
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "analyze_run":
        summary = read_json(Path(arguments["run_dir"]) / "reports" / "summary.json")
        return {
            "service_name": summary.get("service_name"),
            "release_decision": summary.get("release_decision"),
            "features": summary.get("features", {}),
            "bottleneck_analysis": summary.get("bottleneck_analysis", {}),
        }
    if name == "list_runs":
        return {"runs": RunStore(Path(arguments.get("db_path", "./outputs/perfagent.db"))).list_runs(arguments.get("service_name"))}
    if name == "compare_regression":
        summary = read_json(Path(arguments["run_dir"]) / "reports" / "summary.json")
        result = compare_to_latest_baseline(
            RunStore(Path(arguments.get("db_path", "./outputs/perfagent.db"))),
            summary["service_name"],
            summary.get("features", {}),
            exclude_run_id=summary.get("run_id"),
        )
        return result
    if name == "evaluate_service":
        state = evaluate_service(
            service_name=arguments["service_name"],
            openapi_path=Path(arguments["openapi_path"]),
            target_url=arguments["target_url"],
            runtime=arguments.get("runtime", "unknown"),
            slo_p95_ms=int(arguments.get("slo_p95_ms", 500)),
            slo_error_rate_percent=float(arguments.get("slo_error_rate_percent", 1)),
            duration=arguments.get("duration", "10s"),
            output_dir=Path(arguments.get("output_dir", "./outputs/mcp-evaluation")),
            engine=arguments.get("engine", "k6"),
            mode=arguments.get("mode", "standard"),
            prometheus_url=arguments.get("prometheus_url"),
            prometheus_service_label=arguments.get("prometheus_service_label"),
            skip_run=bool(arguments.get("skip_run", False)),
        )
        return {
            "run_id": state["run_id"],
            "service_name": state["service_name"],
            "release_decision": state["release_decision"],
            "features": state["features"],
            "bottleneck_analysis": state["bottleneck_analysis"],
            "react_reasoning": state.get("react_reasoning", {}),
            "report_html_path": state["report_html_path"],
            "report_md_path": state["report_md_path"],
        }
    raise ValueError(f"Unknown MCP tool: {name}")


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    request_id = request.get("id")
    try:
        if method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            params = request.get("params", {})
            result = call_tool(params["name"], params.get("arguments", {}))
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}


def serve_stdio() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    serve_stdio()
