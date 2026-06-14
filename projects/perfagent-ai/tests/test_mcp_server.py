from perfagent.mcp_server import handle_request, list_tools


def test_mcp_lists_perfagent_tools():
    tools = list_tools()

    assert {tool["name"] for tool in tools} >= {"analyze_run", "list_runs", "compare_regression", "evaluate_service"}


def test_mcp_returns_error_for_unknown_method():
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "missing"})

    assert response["id"] == 1
    assert "error" in response


def test_mcp_evaluate_service_returns_report_paths(monkeypatch, tmp_path):
    def fake_evaluate_service(**kwargs):
        return {
            "run_id": "run-1",
            "service_name": kwargs["service_name"],
            "release_decision": "PASS",
            "features": {"stable_rps": 10},
            "bottleneck_analysis": {"bottleneck": "none_detected"},
            "react_reasoning": {"conclusion": {"classification": "no_bottleneck_detected"}},
            "report_html_path": str(tmp_path / "report.html"),
            "report_md_path": str(tmp_path / "report.md"),
        }

    monkeypatch.setattr("perfagent.mcp_server.evaluate_service", fake_evaluate_service)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "evaluate_service",
                "arguments": {
                    "service_name": "payments-api",
                    "openapi_path": "examples/sample-openapi.yaml",
                    "target_url": "http://localhost:8080",
                    "skip_run": True,
                },
            },
        }
    )

    assert response["result"]["release_decision"] == "PASS"
    assert response["result"]["react_reasoning"]["conclusion"]["classification"] == "no_bottleneck_detected"
