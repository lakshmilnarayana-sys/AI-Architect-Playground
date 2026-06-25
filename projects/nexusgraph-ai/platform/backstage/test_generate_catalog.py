from pathlib import Path

from generate_catalog import load_nodes, load_edges, build_entities, validate, _k8s_name


def _root():
    return Path(__file__).resolve().parents[2]


def test_k8s_name_no_double_suffix():
    assert _k8s_name("playback") == "playback-service"
    assert _k8s_name("account-service") == "account-service"


def test_build_entities_counts_and_owner():
    root = _root()
    nodes = load_nodes(root / "graph" / "nodes.csv")
    edges = load_edges(root / "graph" / "edges.csv")
    ents = build_entities(nodes, edges)
    kinds = {}
    for e in ents:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    assert kinds.get("System") == 1
    assert kinds.get("Group") == 13
    assert kinds.get("User") == 12
    assert kinds.get("Component") == 35
    billing = next(e for e in ents if e["kind"] == "Component" and e["metadata"]["name"] == "billing-service")
    assert billing["spec"]["owner"] == "group:billing-platform"
    assert "component:payment-gateway-service" in billing["spec"]["dependsOn"]
    # an imported service with no OWNS_SERVICE edge defaults its owner
    acct = next(e for e in ents if e["kind"] == "Component" and e["metadata"]["name"] == "account-service")
    assert acct["spec"]["owner"] == "group:platform-engineering"


def test_validate_clean():
    root = _root()
    nodes = load_nodes(root / "graph" / "nodes.csv")
    edges = load_edges(root / "graph" / "edges.csv")
    problems = validate(build_entities(nodes, edges))
    assert problems == [], f"validation problems: {problems}"
