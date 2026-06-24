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


def test_render_service_avoids_doubled_service_suffix():
    svc = {"id": "service:account-service", "short": "account-service", "tier": "internal"}
    out = render_service(svc, ["service:auth-service", "service:playback"], "img:dev")
    # own name must not be doubled
    assert "name: account-service\n" in out or "name: account-service " in out
    assert "account-service-service" not in out
    # downstream that already ends in -service -> host not doubled
    assert "auth-service=auth-service:8080/" in out
    # downstream that does NOT end in -service -> gets suffix
    assert "playback=playback-service:8080/" in out
