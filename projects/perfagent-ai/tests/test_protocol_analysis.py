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


def test_analyze_protocol_metrics_flags_web_vitals_and_streaming_metrics():
    result = analyze_protocol_metrics(
        {
            "protocol_metrics": {
                "grpc_method_latency_ms": {"PaymentService/Authorize": 750},
                "reconnects": 1,
                "backpressure_events": 2,
            },
            "browser_metrics": {"lcp_ms": 3200, "inp_ms": 250, "cls": 0.04},
        },
        [],
    )

    types = {finding["type"] for finding in result["findings"]}
    assert "grpc_method_latency" in types
    assert "websocket_reconnects" in types
    assert "websocket_backpressure_events" in types
    assert "browser_web_vital" in types
