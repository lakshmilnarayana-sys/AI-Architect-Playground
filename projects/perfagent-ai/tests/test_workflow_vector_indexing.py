from perfagent.core.artifacts import write_json
from perfagent.workflow import _index_run_vectors


def test_index_run_vectors_uses_configured_vector_dsn(tmp_path, monkeypatch):
    report = tmp_path / "reports" / "report.md"
    summary = tmp_path / "reports" / "summary.json"
    log = tmp_path / "raw" / "execution.log"
    report.parent.mkdir(parents=True)
    log.parent.mkdir(parents=True)
    report.write_text("report narrative")
    write_json(summary, {"service_name": "payments-api"})
    log.write_text("execution log")
    calls = {}

    class FakeVectorStore:
        def __init__(self, dsn):
            calls["dsn"] = dsn

    def fake_index(store, **kwargs):
        calls["kwargs"] = kwargs
        return 3

    monkeypatch.setattr("perfagent.workflow.PgVectorStore", FakeVectorStore)
    monkeypatch.setattr("perfagent.workflow.index_run_narratives", fake_index)

    state = {
        "run_id": "run-1",
        "output_dir": str(tmp_path),
        "report_md_path": str(report),
        "warnings": [],
    }
    _index_run_vectors({"vector_dsn": "postgresql://vector"}, state)

    assert calls["dsn"] == "postgresql://vector"
    assert calls["kwargs"]["run_id"] == "run-1"
    assert calls["kwargs"]["report_text"] == "report narrative"
    assert state["warnings"] == []
