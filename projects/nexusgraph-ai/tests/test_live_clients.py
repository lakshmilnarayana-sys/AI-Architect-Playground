import os
import src.incident.live_clients as lc


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    assert lc.live_enabled() is False


def test_live_enabled_truthy(monkeypatch):
    monkeypatch.setenv("INCIDENT_LIVE", "true")
    assert lc.live_enabled() is True


def test_endpoint_defaults(monkeypatch):
    monkeypatch.delenv("SLACK_MOCK_URL", raising=False)
    assert lc.endpoint("slack") == "http://localhost:18100"


def test_http_post_json_returns_none_on_error(monkeypatch):
    # unreachable port → None, never raises
    assert lc.http_post_json("http://localhost:1/none", {"a": 1}) is None


def test_post_to_slack_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.slack import post_to_slack
    assert post_to_slack("#inc", "hi") is None


def test_create_issue_live_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.jira import create_issue_live
    assert create_issue_live({"incident": {"id": "x"}}) is None
