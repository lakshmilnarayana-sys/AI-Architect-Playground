from pathlib import Path

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.config import load_run_config, resolve_evaluate_options
from perfagent.core.artifacts import write_json


runner = CliRunner()


def test_load_run_config_and_cli_overrides(tmp_path):
    config = tmp_path / "perfagent.yaml"
    config.write_text(
        """
service_name: payments-api
runtime: go
target_url: http://localhost:8080
openapi_path: ./examples/sample-openapi.yaml
slo:
  p95_latency_ms: 500
  error_rate_percent: 1
test:
  duration: 30s
  engine: locust
  mode: capacity
output:
  directory: ./outputs/payments-api
""".lstrip()
    )

    loaded = load_run_config(config)
    resolved = resolve_evaluate_options(loaded, {"engine": "jmeter", "duration": None})

    assert resolved["service_name"] == "payments-api"
    assert resolved["engine"] == "jmeter"
    assert resolved["mode"] == "capacity"
    assert resolved["duration"] == "30s"


def test_evaluate_accepts_config_engine_and_capacity_mode(tmp_path):
    output = tmp_path / "run"
    config = tmp_path / "perfagent.yaml"
    config.write_text(
        f"""
service_name: payments-api
runtime: go
target_url: http://localhost:8080
openapi_path: examples/sample-openapi.yaml
slo:
  p95_latency_ms: 500
  error_rate_percent: 1
test:
  duration: 10s
  engine: k6
  mode: capacity
output:
  directory: {output}
""".lstrip()
    )

    result = runner.invoke(app, ["evaluate", "--config", str(config), "--skip-run"])

    assert result.exit_code == 0, result.output
    state = (output / "state" / "evaluation_state.json").read_text()
    assert '"engine": "k6"' in state
    assert '"mode": "capacity"' in state
    assert "capacity_probe" in (output / "processed" / "test_strategy.yaml").read_text()


def test_baseline_save_and_compare(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "reports").mkdir(parents=True)
    write_json(
        run_dir / "reports" / "summary.json",
        {
            "service_name": "payments-api",
            "features": {"stable_rps": 100, "max_p95_latency_ms": 200, "max_error_rate_percent": 0.2},
        },
    )
    baseline_dir = tmp_path / "baselines"

    save = runner.invoke(
        app,
        ["baseline", "save", "--run-dir", str(run_dir), "--baseline-dir", str(baseline_dir)],
    )
    compare = runner.invoke(
        app,
        ["baseline", "compare", "--run-dir", str(run_dir), "--baseline-dir", str(baseline_dir)],
    )

    assert save.exit_code == 0, save.output
    assert compare.exit_code == 0, compare.output
    assert (baseline_dir / "payments-api.json").exists()
    assert "p95 latency delta: 0.0" in compare.output
