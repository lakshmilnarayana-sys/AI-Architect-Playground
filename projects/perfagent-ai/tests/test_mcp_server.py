from perfagent.mcp_server import handle_request, list_tools


def test_mcp_lists_perfagent_tools():
    tools = list_tools()

    assert {tool["name"] for tool in tools} >= {"analyze_run", "list_runs", "compare_regression"}


def test_mcp_returns_error_for_unknown_method():
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "missing"})

    assert response["id"] == 1
    assert "error" in response
