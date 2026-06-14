import subprocess

from perfagent.core.artifacts import write_json
from perfagent.executors import capacity_search


def test_build_capacity_probe_rps_uses_bounded_range():
    assert capacity_search.build_capacity_probe_rps(min_rps=50, max_rps=400, steps=4) == [50, 100, 200, 400]


def test_run_capacity_search_stops_at_first_failure(tmp_path, monkeypatch):
    openapi = tmp_path / "openapi.yaml"
    openapi.write_text("openapi: 3.0.0\ninfo: {title: t, version: v}\npaths: {}\n")
    decisions = ["PASS", "WARN"]

    def fake_run(command, text, capture_output, check):
        probe_dir = tmp_path / "capacity" / f"probe-{command[command.index('--capacity-probe-rps') + 1]}rps"
        decision = decisions.pop(0)
        write_json(
            probe_dir / "reports" / "summary.json",
            {
                "release_decision": decision,
                "features": {"max_p95_latency_ms": 100 if decision == "PASS" else 900, "max_error_rate_percent": 0},
            },
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(capacity_search.subprocess, "run", fake_run)

    result = capacity_search.run_capacity_search(
        service_name="payments-api",
        openapi_path=openapi,
        target_url="http://localhost:8080",
        runtime="python",
        slo_p95_ms=500,
        slo_error_rate_percent=1,
        duration="10s",
        output_dir=tmp_path / "capacity",
        min_rps=50,
        max_rps=100,
        steps=2,
    )

    assert result["estimated_capacity_rps"] == 50
    assert result["breaking_point_rps"] == 100
    assert len(result["probes"]) == 2
