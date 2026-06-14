from datetime import UTC, datetime

from perfagent.analyzers.bottlenecks import classify_bottleneck
from perfagent.collectors import prometheus_collector as collector
from perfagent.config import load_run_config, resolve_evaluate_options
from perfagent.generators.report_renderer import render_reports


def test_config_loads_dependency_definitions(tmp_path):
    config = tmp_path / "perfagent.yaml"
    config.write_text(
        """
service_name: payments-api
dependencies:
  postgres:
    type: postgres
    role: downstream
    criticality: high
    metrics:
      p95_latency_ms: 'pg_query_p95{service="{service}"}'
      connection_pool_utilization_percent: 'pg_pool_utilization{service="{service}"}'
""".lstrip()
    )

    resolved = resolve_evaluate_options(load_run_config(config), {})

    assert resolved["dependencies"][0]["name"] == "postgres"
    assert resolved["dependencies"][0]["type"] == "postgres"
    assert "p95_latency_ms" in resolved["dependencies"][0]["metrics"]


def test_collect_dependency_prometheus_metrics(monkeypatch):
    calls = []

    def fake_query(url, query, start, end, step):
        calls.append(query)
        return [{"timestamp": "2026-06-13T10:00:00Z", "value": 88.0}]

    monkeypatch.setattr(collector, "_query_range", fake_query)

    result = collector.collect_dependency_metrics(
        "https://prom.example.com",
        "payments-api",
        [
            {
                "name": "postgres",
                "type": "postgres",
                "metrics": {"p95_latency_ms": 'pg_query_p95{service="{service}"}'},
            }
        ],
        start=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
    )

    assert result["dependencies"]["postgres"]["metrics"]["p95_latency_ms"][0]["value"] == 88.0
    assert calls == ['pg_query_p95{service="payments-api"}']


def test_merge_dependency_metrics_into_aligned_rows():
    rows = [{"timestamp": "2026-06-13T10:00:00Z", "phase": "stress", "p95_latency_ms": 700, "rps": 500}]
    metrics = {
        "dependencies": {
            "postgres": {
                "type": "postgres",
                "metrics": {
                    "p95_latency_ms": [{"timestamp": "2026-06-13T10:00:00Z", "value": 650.0}],
                    "connection_pool_utilization_percent": [{"timestamp": "2026-06-13T10:00:00Z", "value": 99.0}],
                },
            }
        }
    }

    merged = collector.merge_dependency_metrics(rows, metrics)

    assert merged[0]["dep_postgres_p95_latency_ms"] == 650.0
    assert merged[0]["dep_postgres_connection_pool_utilization_percent"] == 99.0


def test_dependency_bottleneck_rule_detects_database_pool_saturation():
    result = classify_bottleneck(
        {
            "max_p95_latency_ms": 900,
            "slo_p95_latency_ms": 500,
            "max_error_rate_percent": 0.2,
            "slo_error_rate_percent": 1,
            "cpu_peak_percent": 40,
            "memory_peak_mb": 512,
            "dependency_findings": [
                {
                    "dependency": "postgres",
                    "type": "postgres",
                    "metric": "connection_pool_utilization_percent",
                    "value": 99,
                    "threshold": 90,
                }
            ],
        }
    )

    assert result["bottleneck"] == "database_connection_pool_saturation"
    assert "postgres" in " ".join(result["evidence"])


def test_report_includes_dependency_analysis_section(tmp_path):
    paths = render_reports(
        output_dir=tmp_path,
        service_name="payments-api",
        runtime="go",
        target_url="http://localhost:8080",
        strategy={"duration": "1m", "stages": []},
        contract_analysis={"endpoints": []},
        features={
            "release_decision": "WARN",
            "max_p95_latency_ms": 900,
            "slo_p95_latency_ms": 500,
            "max_error_rate_percent": 0.2,
            "slo_error_rate_percent": 1,
            "stable_rps": 400,
            "dependency_findings": [{"dependency": "postgres", "metric": "p95_latency_ms", "value": 650}],
        },
        bottleneck_analysis={"bottleneck": "database_latency", "confidence": "medium", "evidence": [], "recommendations": []},
        dependency_analysis={
            "dependencies": [{"name": "postgres", "type": "postgres", "role": "downstream", "criticality": "high"}],
            "findings": [{"dependency": "postgres", "metric": "p95_latency_ms", "value": 650}],
        },
        aligned_timeseries=[],
    )

    markdown = paths["report_md_path"].read_text()
    html = paths["report_html_path"].read_text()
    assert "## Dependency Analysis" in markdown
    assert "postgres" in markdown
    assert 'id="dependency-analysis"' in html
