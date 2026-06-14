from __future__ import annotations

from datetime import UTC, datetime

from perfagent.collectors import prometheus_collector as collector


def test_collect_prometheus_metrics_queries_remote_query_range(monkeypatch):
    calls = []

    def fake_query(url, query, start, end, step):
        calls.append((url, query, start, end, step))
        if query.startswith("sum(rate(container_cpu_usage_seconds_total"):
            return [{"timestamp": "2026-06-13T10:00:00Z", "value": 42.0}]
        return []

    monkeypatch.setattr(collector, "_query_range", fake_query)

    result = collector.collect_prometheus_metrics(
        "https://prom.example.com",
        "payments-api",
        start=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
        step_seconds=10,
    )

    assert result["enabled"] is True
    assert result["url"] == "https://prom.example.com"
    assert result["service_label"] == "payments-api"
    assert result["metrics"]["cpu_percent"] == [{"timestamp": "2026-06-13T10:00:00Z", "value": 42.0}]
    assert any('pod=~".*payments-api.*"' in call[1] for call in calls)


def test_collect_prometheus_metrics_uses_custom_query_config(monkeypatch):
    calls = []

    def fake_query(url, query, start, end, step):
        calls.append((url, query, start, end, step))
        return [{"timestamp": "2026-06-13T10:00:00Z", "value": 99.0}]

    monkeypatch.setattr(collector, "_query_range", fake_query)

    result = collector.collect_prometheus_metrics(
        "https://prom.example.com",
        "payments-api",
        start=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        end=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
        step_seconds=10,
        query_templates={
            "cpu_percent": 'avg(rate(process_cpu_seconds_total{app="{service}"}[2m])) * 100',
            "memory_mb": 'avg(process_resident_memory_bytes{app="{service}"}) / 1024 / 1024',
        },
    )

    assert set(result["metrics"]) == {"cpu_percent", "memory_mb"}
    assert calls[0][1] == 'avg(rate(process_cpu_seconds_total{app="payments-api"}[2m])) * 100'
    assert result["query_names"] == ["cpu_percent", "memory_mb"]


def test_load_prometheus_query_config_supports_yaml(tmp_path):
    config_path = tmp_path / "prometheus-queries.yaml"
    config_path.write_text(
        """
queries:
  cpu_percent: avg(rate(process_cpu_seconds_total{job="{service}"}[1m])) * 100
  memory_mb: process_resident_memory_bytes{job="{service}"} / 1024 / 1024
""".lstrip()
    )

    queries = collector.load_prometheus_query_config(config_path)

    assert queries == {
        "cpu_percent": 'avg(rate(process_cpu_seconds_total{job="{service}"}[1m])) * 100',
        "memory_mb": 'process_resident_memory_bytes{job="{service}"} / 1024 / 1024',
    }


def test_query_range_parses_prometheus_matrix_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"""{
              "status": "success",
              "data": {
                "resultType": "matrix",
                "result": [
                  {"metric": {}, "values": [[1781344800, "12.5"], [1781344810, "13.5"]]}
                ]
              }
            }"""

    monkeypatch.setattr(collector.request, "urlopen", lambda req, timeout: Response())

    rows = collector._query_range(
        "https://prom.example.com",
        "up",
        datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
        10,
    )

    assert rows == [
        {"timestamp": "2026-06-13T10:00:00Z", "value": 12.5},
        {"timestamp": "2026-06-13T10:00:10Z", "value": 13.5},
    ]


def test_merge_prometheus_metrics_into_aligned_rows():
    rows = [
        {"timestamp": "2026-06-13T10:00:00Z", "phase": "baseline", "rps": 100, "cpu_percent": 0, "memory_mb": 0, "cpu_throttling_percent": 0},
        {"timestamp": "2026-06-13T10:00:10Z", "phase": "stress", "rps": 200, "cpu_percent": 0, "memory_mb": 0, "cpu_throttling_percent": 0},
    ]
    metrics = {
        "metrics": {
            "cpu_percent": [{"timestamp": "2026-06-13T10:00:10Z", "value": 77.0}],
            "memory_mb": [{"timestamp": "2026-06-13T10:00:10Z", "value": 512.0}],
            "cpu_throttling_percent": [{"timestamp": "2026-06-13T10:00:10Z", "value": 6.5}],
        }
    }

    merged = collector.merge_prometheus_metrics(rows, metrics)

    assert merged[0]["cpu_percent"] == 0
    assert merged[1]["cpu_percent"] == 77.0
    assert merged[1]["memory_mb"] == 512.0
    assert merged[1]["cpu_throttling_percent"] == 6.5


def test_validate_prometheus_queries_reports_available_and_missing(monkeypatch):
    def fake_query(url, query, start, end, step):
        if "missing_metric" in query:
            return []
        return [{"timestamp": "2026-06-13T10:00:00Z", "value": 1.0}]

    monkeypatch.setattr(collector, "_query_range", fake_query)

    result = collector.validate_prometheus_queries(
        "https://prom.example.com",
        "payments-api",
        query_templates={"cpu_percent": "up", "memory_mb": "missing_metric"},
    )

    assert result["status"] == "failed"
    assert result["results"]["cpu_percent"]["available"] is True
    assert result["results"]["memory_mb"]["available"] is False
