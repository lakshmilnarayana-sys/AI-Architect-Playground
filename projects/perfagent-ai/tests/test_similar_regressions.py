from perfagent.analyzers.similar_regressions import find_similar_regressions


def test_find_similar_regressions_combines_sql_candidates_and_vector_matches():
    result = find_similar_regressions(
        query="p95 latency regression during stress",
        service_name="payments-api",
        runs=[
            {
                "run_id": "run-pass",
                "service_name": "payments-api",
                "release_decision": "PASS",
                "features_json": '{"max_p95_latency_ms": 120, "max_error_rate_percent": 0.1}',
            },
            {
                "run_id": "run-warn",
                "service_name": "payments-api",
                "release_decision": "WARN",
                "features_json": '{"max_p95_latency_ms": 820, "max_error_rate_percent": 2.2, "breaking_point_rps": 500}',
            },
        ],
        vector_matches=[
            {"run_id": "run-warn", "chunk_type": "report", "chunk_index": 0, "distance": 0.12},
        ],
    )

    assert result["sql_candidates"][0]["run_id"] == "run-warn"
    assert result["vector_matches"][0]["run_id"] == "run-warn"
    assert "Structured history found" in result["summary"]
