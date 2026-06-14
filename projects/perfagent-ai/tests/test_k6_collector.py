from pathlib import Path

from perfagent.collectors.k6_collector import build_k6_command, run_k6


def test_build_k6_command_prefers_native_binary(tmp_path):
    script = tmp_path / "generated" / "perf_test.js"
    summary = tmp_path / "raw" / "k6_summary.json"
    timeseries = tmp_path / "raw" / "k6_timeseries.jsonl"
    script.parent.mkdir()
    script.write_text("export default function () {}\n")

    command = build_k6_command(
        script,
        summary,
        timeseries,
        k6_path="/opt/homebrew/bin/k6",
        docker_path="/usr/local/bin/docker",
    )

    assert command == [
        "/opt/homebrew/bin/k6",
        "run",
        "--summary-export",
        str(summary),
        "--out",
        f"json={timeseries}",
        str(script),
    ]


def test_build_k6_command_uses_docker_fallback_with_mounted_workspace(tmp_path):
    script = tmp_path / "generated" / "perf_test.js"
    summary = tmp_path / "raw" / "k6_summary.json"
    timeseries = tmp_path / "raw" / "k6_timeseries.jsonl"
    script.parent.mkdir()
    summary.parent.mkdir()
    script.write_text("export default function () {}\n")

    command = build_k6_command(
        script,
        summary,
        timeseries,
        k6_path=None,
        docker_path="/usr/local/bin/docker",
    )

    assert command[:5] == ["/usr/local/bin/docker", "run", "--rm", "-v", f"{tmp_path}:/work"]
    assert command[-7:] == [
        "grafana/k6:latest",
        "run",
        "--summary-export",
        "/work/raw/k6_summary.json",
        "--out",
        "json=/work/raw/k6_timeseries.jsonl",
        "/work/generated/perf_test.js",
    ]


def test_run_k6_skips_when_native_and_docker_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("perfagent.collectors.k6_collector.shutil.which", lambda name: None)
    script = tmp_path / "generated" / "perf_test.js"
    summary = tmp_path / "raw" / "k6_summary.json"
    timeseries = tmp_path / "raw" / "k6_timeseries.jsonl"
    log = tmp_path / "raw" / "execution.log"
    script.parent.mkdir()
    script.write_text("export default function () {}\n")

    result = run_k6(script, summary, timeseries, log)

    assert result["exit_code"] == 127
    assert result["skipped"] is True
    assert result["runtime"] == "missing"
    assert result["timeseries_path"] == str(timeseries)
    assert "k6 executable not found and Docker fallback is unavailable" in result["stderr"]
