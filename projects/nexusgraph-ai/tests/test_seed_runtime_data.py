from src.incident.jira import query_incident_metrics, set_store_path
from src.seed_runtime_data import seed_all, seed_fallback_stores, seed_neo4j_graph


def test_seed_fallback_stores_creates_jira_history(tmp_path):
    set_store_path(tmp_path / "jira.yaml")

    result = seed_fallback_stores()
    metrics = query_incident_metrics()

    assert result["status"] == "seeded"
    assert result["jira"]["seeded"] >= 1
    assert metrics["total_incidents"] >= result["jira"]["seeded"]
    assert metrics["by_severity"]


def test_seed_all_can_skip_external_neo4j_and_preserve_fallbacks(tmp_path, monkeypatch):
    set_store_path(tmp_path / "jira.yaml")
    monkeypatch.setattr("src.seed_runtime_data.seed_vector_store", lambda force=False: {"status": "existing"})

    result = seed_all(seed_neo4j=False)

    assert result["vector_store"]["status"] == "existing"
    assert result["neo4j_graph"]["status"] == "skipped"
    assert result["fallback_stores"]["jira"]["total"] >= 1


def test_seed_neo4j_graph_skips_unless_enabled():
    assert seed_neo4j_graph(enabled=False) == {"status": "skipped"}
