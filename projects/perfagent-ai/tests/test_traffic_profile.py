from datetime import UTC, datetime

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.config import derive_strategy_from_traffic_profile, load_run_config, resolve_evaluate_options
from perfagent.collectors import traffic_profile as collector
from perfagent.generators.k6_generator import generate_k6_script


runner = CliRunner()


def test_config_loads_production_traffic_profile(tmp_path):
    config = tmp_path / "perfagent.yaml"
    config.write_text(
        """
service_name: payments-api
traffic_profile:
  enabled: true
  source: prometheus
  lookback: 6h
  peak_multiplier: 1.5
  endpoint_label: route
  request_rate_query: 'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))'
""".lstrip()
    )

    resolved = resolve_evaluate_options(load_run_config(config), {})

    assert resolved["traffic_profile"]["enabled"] is True
    assert resolved["traffic_profile"]["source"] == "prometheus"
    assert resolved["traffic_profile"]["peak_multiplier"] == 1.5


def test_collect_prometheus_traffic_profile_derives_endpoint_mix(monkeypatch):
    def fake_query(url, query, start, end, step):
        return [
            {"timestamp": "2026-06-13T10:00:00Z", "value": 80.0, "labels": {"route": "/v1/payments"}},
            {"timestamp": "2026-06-13T10:00:00Z", "value": 20.0, "labels": {"route": "/health"}},
        ]

    monkeypatch.setattr(collector, "_query_range_with_labels", fake_query)

    profile = collector.collect_prometheus_traffic_profile(
        "https://prom.example.com",
        "payments-api",
        {
            "endpoint_label": "route",
            "request_rate_query": 'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))',
            "peak_multiplier": 1.5,
        },
        start=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 13, 10, 5, tzinfo=UTC),
    )

    assert profile["observed_peak_rps"] == 100.0
    assert profile["production_like_rps"] == 100.0
    assert profile["peak_rps"] == 150.0
    assert profile["endpoint_mix"][0]["path"] == "/v1/payments"
    assert profile["endpoint_mix"][0]["weight"] == 0.8


def test_strategy_derived_from_traffic_profile():
    strategy = derive_strategy_from_traffic_profile(
        {
            "production_like_rps": 100,
            "peak_rps": 150,
            "endpoint_mix": [{"path": "/v1/payments", "weight": 0.8}],
        },
        duration="30s",
        slo_p95_ms=500,
        slo_error_rate_percent=1,
    )

    assert strategy["traffic_model"] == "observed-production"
    assert strategy["phases"][1]["target_rps"] == 100
    assert strategy["phases"][2]["target_rps"] == 150
    assert strategy["endpoint_mix"][0]["weight"] == 0.8


def test_k6_script_uses_endpoint_mix_weights(tmp_path):
    contract = {
        "endpoints": [
            {"method": "POST", "path": "/v1/payments", "operation_id": "createPayment", "expected_status": 201},
            {"method": "GET", "path": "/health", "operation_id": "health", "expected_status": 200},
        ]
    }
    test_data = {
        "endpoints": [
            {"operation_id": "createPayment", "method": "POST", "path": "/v1/payments", "headers": {}, "body": {"amount": 1}, "query": {}, "path_params": {}},
            {"operation_id": "health", "method": "GET", "path": "/health", "headers": {}, "body": None, "query": {}, "path_params": {}},
        ]
    }
    strategy = {
        "thresholds": {"p95_latency_ms": 500, "error_rate_percent": 1},
        "stages": [{"duration": "1m", "target": 10}],
        "endpoint_mix": [{"path": "/v1/payments", "weight": 0.8}, {"path": "/health", "weight": 0.2}],
    }

    output = tmp_path / "perf_test.js"
    generate_k6_script(contract, test_data, strategy, "http://localhost:8080", output)

    script = output.read_text()
    assert "const ENDPOINT_MIX" in script
    assert "Math.random()" in script
    assert "if (selected.operation_id === \"createPayment\")" in script


def test_evaluate_production_traffic_profile_writes_artifact(tmp_path, monkeypatch):
    def fake_profile(url, service_label, config, **kwargs):
        return {
            "enabled": True,
            "source": "prometheus",
            "observed_peak_rps": 100,
            "production_like_rps": 100,
            "peak_rps": 150,
            "endpoint_mix": [{"path": "/v1/payments", "weight": 1.0, "observed_rps": 100}],
        }

    monkeypatch.setattr("perfagent.workflow.collect_prometheus_traffic_profile", fake_profile)
    output = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--service-name",
            "payments-api",
            "--openapi",
            "examples/sample-openapi.yaml",
            "--target-url",
            "http://localhost:8080",
            "--runtime",
            "go",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
            "--output",
            str(output),
            "--skip-run",
            "--prometheus-url",
            "https://prom.example.com",
            "--prometheus-service-label",
            "payments-api",
            "--traffic-profile",
            "production",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "processed" / "traffic_profile.json").exists()
    assert "observed-production" in (output / "processed" / "test_strategy.yaml").read_text()
    assert "Production Traffic Profile" in (output / "reports" / "report.md").read_text()
