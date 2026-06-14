from perfagent.analyzers.protocols import analyze_protocol_metrics


def test_analyze_protocol_metrics_flags_grpc_and_websocket_errors():
    result = analyze_protocol_metrics(
        {
            "protocol_metrics": {
                "grpc_status": {"OK": 10, "UNAVAILABLE": 2},
                "websocket_messages": 20,
                "connection_errors": 1,
            }
        },
        [],
    )

    assert result["protocol_metrics"]["grpc_status"]["UNAVAILABLE"] == 2
    assert {finding["type"] for finding in result["findings"]} == {
        "grpc_status_errors",
        "websocket_connection_errors",
    }
