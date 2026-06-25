import re
import textwrap
from pathlib import Path

from generate_manifests import load_services, load_dependencies, render_service


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip())
    return p


def test_load_services_filters_service_rows(tmp_path):
    nodes = _write(tmp_path, "nodes.csv", """
        id,label,name,description
        person:x,Person,X,dev
        service:playback,Service,playback-service,customer-facing
        service:billing,Service,billing-service,customer-facing
    """)
    svcs = load_services(nodes)
    ids = {s["id"] for s in svcs}
    assert ids == {"service:playback", "service:billing"}
    pb = next(s for s in svcs if s["id"] == "service:playback")
    assert pb["short"] == "playback"
    assert pb["tier"] == "customer-facing"


def test_load_dependencies(tmp_path):
    edges = _write(tmp_path, "edges.csv", """
        source,relationship,target
        person:x,MEMBER_OF,team:y
        service:playback,DEPENDS_ON,service:manifest
        service:playback,DEPENDS_ON,service:identity
    """)
    deps = load_dependencies(edges)
    assert deps["service:playback"] == ["service:manifest", "service:identity"]


def test_render_service_includes_downstreams_env():
    svc = {"id": "service:playback", "short": "playback", "tier": "customer-facing"}
    out = render_service(svc, ["service:manifest", "service:identity"], "img:dev")
    assert "name: playback-service" in out
    assert "kind: Deployment" in out
    assert "kind: Service" in out
    assert "manifest-service:8080" in out
    assert "identity-service:8080" in out
    assert "SERVICE_TIER" in out and "customer-facing" in out
    # Port must be named 'http' for Prometheus-Operator ServiceMonitor compatibility
    assert "name: http" in out


def test_render_service_avoids_doubled_service_suffix():
    svc = {"id": "service:account-service", "short": "account-service", "tier": "internal"}
    out = render_service(svc, ["service:auth-service", "service:playback"], "img:dev")
    # own name must not be doubled
    assert "name: account-service\n" in out or "name: account-service " in out
    assert "account-service-service" not in out
    # downstream that already ends in -service -> host not doubled
    assert "auth-service=http://auth-service:8080/" in out
    # downstream that does NOT end in -service -> gets suffix
    assert "playback=http://playback-service:8080/" in out


def test_safe_label_sanitizes_invalid_description():
    from generate_manifests import _safe_label
    raw = "Imported from Netflix synthetic dataset: Service account-service"
    result = _safe_label(raw)
    assert len(result) <= 63
    assert re.match(r'^[A-Za-z0-9]', result)
    assert re.search(r'[A-Za-z0-9]$', result)
    assert ':' not in result and ' ' not in result


def test_safe_label_empty_returns_unknown():
    from generate_manifests import _safe_label
    assert _safe_label("") == "unknown"
    assert _safe_label(":::") == "unknown"


def test_render_service_sets_otel_endpoint():
    svc = {"id": "service:playback", "short": "playback", "tier": "customer-facing"}
    out = render_service(svc, [], "img:dev")
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in out
    assert "tempo.observability.svc:4318" in out


def test_service_tier_normalized():
    from generate_manifests import _normalize_tier
    assert _normalize_tier("customer-facing") == "customer-facing"
    assert _normalize_tier("internal") == "internal"
    assert _normalize_tier("Imported from Netflix synthetic dataset: Service account-service") == "internal"
    assert _normalize_tier("") == "internal"
