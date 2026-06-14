from perfagent.ci.pr_complexity import classify_pr_complexity


def test_classify_pr_complexity_triggers_full_run_for_service_and_db_changes():
    result = classify_pr_complexity(
        [
            "services/payments/api.py",
            "migrations/20260614_add_index.sql",
            "docker-compose.yml",
            "README.md",
        ]
    )

    assert result["level"] == "high"
    assert result["recommended_profile"] == "full-regression"
    assert "database migration changed" in result["reasons"]


def test_classify_pr_complexity_allows_smoke_for_docs_only():
    result = classify_pr_complexity(["README.md", "docs/perf.md"])

    assert result["level"] == "low"
    assert result["recommended_profile"] == "smoke"
