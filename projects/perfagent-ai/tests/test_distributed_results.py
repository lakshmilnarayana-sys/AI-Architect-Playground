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
