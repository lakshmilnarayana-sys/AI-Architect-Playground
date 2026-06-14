import json
from datetime import UTC, datetime

from perfagent.collectors import observability_adapters as adapters


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_datadog_adapter_derives_endpoint_mix(monkeypatch):
    def fake_urlopen(req, timeout):
        return FakeResponse(
            {
                "series": [
                    {"tag_set": ["resource_name:/v1/payments"], "pointlist": [[1, 80]]},
                    {"tag_set": ["resource_name:/health"], "pointlist": [[1, 20]]},
                ]
            }
        )

    monkeypatch.setattr(adapters.request, "urlopen", fake_urlopen)

    profile = adapters.collect_datadog_traffic_profile(
        {"provider": "datadog", "api_key": "x", "app_key": "y", "peak_multiplier": 2},
        "payments-api",
        start=datetime(2026, 6, 13, 10, tzinfo=UTC),
        end=datetime(2026, 6, 13, 11, tzinfo=UTC),
    )

    assert profile["source"] == "datadog"
    assert profile["peak_rps"] == 200
    assert profile["endpoint_mix"][0]["path"] == "/v1/payments"
    assert profile["endpoint_mix"][0]["weight"] == 0.8


def test_newrelic_adapter_derives_endpoint_mix(monkeypatch):
    def fake_urlopen(req, timeout):
        return FakeResponse(
            {
                "data": {
                    "actor": {
                        "account": {
                            "nrql": {
                                "results": [
                                    {"request.uri": "/v1/payments", "rps": 30},
                                    {"request.uri": "/health", "rps": 10},
                                ]
                            }
                        }
                    }
                }
            }
        )

    monkeypatch.setattr(adapters.request, "urlopen", fake_urlopen)

    profile = adapters.collect_newrelic_traffic_profile(
        {"provider": "newrelic", "account_id": 123, "api_key": "x"},
        "payments-api",
        start=datetime(2026, 6, 13, 10, tzinfo=UTC),
        end=datetime(2026, 6, 13, 11, tzinfo=UTC),
    )

    assert profile["production_like_rps"] == 40
    assert profile["endpoint_mix"][0]["path"] == "/v1/payments"


def test_elasticsearch_adapter_derives_endpoint_mix(monkeypatch):
    def fake_urlopen(req, timeout):
        return FakeResponse(
            {
                "aggregations": {
                    "endpoints": {
                        "buckets": [
                            {"key": "/v1/payments", "doc_count": 3600},
                            {"key": "/health", "doc_count": 1800},
                        ]
                    }
                }
            }
        )

    monkeypatch.setattr(adapters.request, "urlopen", fake_urlopen)

    profile = adapters.collect_elasticsearch_traffic_profile(
        {"provider": "elasticsearch", "base_url": "http://elastic:9200", "index": "traces-*"},
        "payments-api",
        start=datetime(2026, 6, 13, 10, tzinfo=UTC),
        end=datetime(2026, 6, 13, 11, tzinfo=UTC),
    )

    assert profile["observed_peak_rps"] == 1.5
    assert profile["endpoint_mix"][0]["path"] == "/v1/payments"


def test_build_provider_query_pack_renders_queries():
    pack = adapters.build_provider_query_pack("datadog", "payments-api", {})

    assert pack["supported"] is True
    assert "payments-api" in pack["queries"]["request_rate"]
    assert "api_key" in pack["required_config"]
    assert "cpu_usage" in pack["golden_signals"]
    assert "postgres" in pack["dependency_queries"]


def test_validate_provider_query_pack_reports_missing_config():
    pack = adapters.validate_provider_query_pack("newrelic", "payments-api", {"api_key": "key"})

    assert pack["valid"] is False
    assert pack["missing_config"] == ["account_id"]
