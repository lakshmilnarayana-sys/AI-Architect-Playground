from typer.testing import CliRunner

from perfagent.ci.pr_comment import format_pr_comment
from perfagent.cli import app
from perfagent.core.artifacts import write_json


runner = CliRunner()


def test_format_pr_comment_includes_decision_metrics_and_regression():
    comment = format_pr_comment(
        {
            "service_name": "payments-api",
            "release_decision": "WARN",
            "features": {"stable_rps": 100, "max_p95_latency_ms": 700},
            "bottleneck_analysis": {"bottleneck": "dependency_or_unknown", "confidence": "medium"},
        },
        {"regression_detected": True, "findings": ["p95 latency regressed by 30.0%"]},
    )

    assert "PerfAgent Performance Report" in comment
    assert "Decision: `WARN`" in comment
    assert "p95 latency regressed" in comment


def test_ci_comment_command_writes_markdown(tmp_path):
    summary = tmp_path / "summary.json"
    output = tmp_path / "comment.md"
    write_json(
        summary,
        {
            "service_name": "payments-api",
            "release_decision": "PASS",
            "features": {"stable_rps": 100},
            "bottleneck_analysis": {"bottleneck": "none_detected", "confidence": "medium"},
        },
    )

    result = runner.invoke(app, ["ci", "comment", "--summary", str(summary), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert "Decision: `PASS`" in output.read_text()
