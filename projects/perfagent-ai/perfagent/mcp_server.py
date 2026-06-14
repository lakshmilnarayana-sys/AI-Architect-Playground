from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from perfagent.core.artifacts import read_json
from perfagent.storage.run_store import RunStore, compare_to_latest_baseline


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
