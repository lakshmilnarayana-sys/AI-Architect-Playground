from perfagent.collectors.distributed_results import merge_worker_summaries


def test_merge_worker_summaries_combines_counts_and_uses_worst_latency(tmp_path):
    first = tmp_path / "worker-1.json"
    second = tmp_path / "worker-2.json"
    first.write_text(
        """{"metrics":{"http_reqs":{"count":100,"rate":10},"http_req_duration":{"percentiles":{"p(95)":200,"p(99)":300}},"http_req_failed":{"rate":0.01}}}"""
    )
    second.write_text(
        """{"metrics":{"http_reqs":{"count":150,"rate":15},"http_req_duration":{"percentiles":{"p(95)":450,"p(99)":700}},"http_req_failed":{"rate":0.02}}}"""
    )

    summary, aligned = merge_worker_summaries([first, second])

    assert summary["metrics"]["http_reqs"]["count"] == 250
    assert summary["metrics"]["http_reqs"]["rate"] == 25
    assert summary["metrics"]["http_req_duration"]["p(95)"] == 450
    assert summary["metrics"]["http_req_failed"]["rate"] == 0.016
    assert aligned[0]["p95_latency_ms"] == 450


def test_merge_worker_summaries_preserves_worker_browser_and_protocol_metadata(tmp_path):
    first = tmp_path / "worker-1.json"
    second = tmp_path / "worker-2.json"
    first.write_text(
        """{"worker_metadata":{"worker_id":"worker-1","region":"eu-west-2"},"metrics":{"http_reqs":{"count":2,"rate":1},"http_req_duration":{"p(95)":20,"p(99)":25},"http_req_failed":{"rate":0}},"browser_metrics":{"first_contentful_paint_ms":80},"protocol_metrics":{"grpc_status":{"OK":2},"websocket_messages":4,"connection_errors":0}}"""
    )
    second.write_text(
        """{"worker_metadata":{"worker_id":"worker-2","region":"us-east-1"},"metrics":{"http_reqs":{"count":3,"rate":1.5},"http_req_duration":{"p(95)":45,"p(99)":55},"http_req_failed":{"rate":0.3333333333}},"browser_metrics":{"first_contentful_paint_ms":100},"protocol_metrics":{"grpc_status":{"OK":2,"UNAVAILABLE":1},"websocket_messages":6,"connection_errors":1}}"""
    )

    summary, aligned = merge_worker_summaries([first, second])

    assert summary["worker_metadata"] == [
        {"path": str(first), "worker_id": "worker-1", "region": "eu-west-2"},
        {"path": str(second), "worker_id": "worker-2", "region": "us-east-1"},
    ]
    assert summary["browser_metrics"]["first_contentful_paint_ms"] == 90
    assert summary["protocol_metrics"]["grpc_status"] == {"OK": 4, "UNAVAILABLE": 1}
    assert summary["protocol_metrics"]["websocket_messages"] == 10
    assert summary["protocol_metrics"]["connection_errors"] == 1
    assert aligned[0]["browser_first_contentful_paint_ms"] == 90
    assert aligned[0]["grpc_status"] == '{"OK":4,"UNAVAILABLE":1}'
    assert aligned[0]["websocket_messages"] == 10
    assert aligned[0]["connection_errors"] == 1
