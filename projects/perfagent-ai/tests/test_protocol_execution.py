from perfagent.collectors.protocol_collectors import duration_to_seconds, protocol_result_to_summary, run_protocol_script


def test_protocol_result_to_summary_normalizes_websocket_rows():
    summary = protocol_result_to_summary(
        [
            {"requests": 2, "errors": 1, "latencies_ms": [10, 20]},
            {"requests": 1, "errors": 0, "latencies_ms": [30]},
        ],
        elapsed_seconds=3,
    )

    assert summary["metrics"]["http_reqs"]["count"] == 3
    assert summary["metrics"]["http_reqs"]["rate"] == 1
    assert summary["metrics"]["http_req_failed"]["rate"] == 1 / 3
    assert summary["metrics"]["http_req_duration"]["p(95)"] == 30


def test_run_protocol_script_executes_json_harness(tmp_path):
    script = tmp_path / "harness.py"
    script.write_text(
        """
import argparse
import json
parser = argparse.ArgumentParser()
parser.add_argument("--duration-seconds", type=int)
parser.add_argument("--connections", type=int)
args = parser.parse_args()
print(json.dumps([{"requests": 4, "errors": 1, "latencies_ms": [5, 10, 15, 20]}]))
""".lstrip()
    )

    execution, summary, aligned = run_protocol_script(
        tool="websocket",
        script_path=script,
        summary_path=tmp_path / "summary.json",
        execution_log_path=tmp_path / "execution.log",
        duration_seconds=1,
        concurrency=2,
    )

    assert execution["exit_code"] == 0
    assert summary["metrics"]["http_reqs"]["count"] == 4
    assert aligned[0]["error_rate_percent"] == 25
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "execution.log").exists()


def test_duration_to_seconds_parses_units():
    assert duration_to_seconds("500ms") == 1
    assert duration_to_seconds("2m") == 120
