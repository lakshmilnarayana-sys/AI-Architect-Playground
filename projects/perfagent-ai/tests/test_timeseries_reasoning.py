from perfagent.analyzers.timeseries_reasoning import analyze_timeseries, reason_over_timeseries


def test_timeseries_reasoning_correlates_load_and_detects_breakpoint():
    rows = [
        {"timestamp": "2026-06-14T10:00:00Z", "phase": "warmup", "rps": 50, "p95_latency_ms": 120, "error_rate_percent": 0.0, "cpu_percent": 35},
        {"timestamp": "2026-06-14T10:00:10Z", "phase": "baseline", "rps": 200, "p95_latency_ms": 240, "error_rate_percent": 0.1, "cpu_percent": 42},
        {"timestamp": "2026-06-14T10:00:20Z", "phase": "stress", "rps": 500, "p95_latency_ms": 820, "error_rate_percent": 2.4, "cpu_percent": 55},
        {"timestamp": "2026-06-14T10:00:30Z", "phase": "recovery", "rps": 50, "p95_latency_ms": 180, "error_rate_percent": 0.2, "cpu_percent": 38},
    ]

    analysis = analyze_timeseries(rows, slo_p95_ms=500, slo_error_rate_percent=1)
    reasoning = reason_over_timeseries(
        timeseries_analysis=analysis,
        features={"estimated_capacity_rps": 200, "breaking_point_rps": 500, "first_slo_breach_phase": "stress"},
        dependency_analysis={"dependencies": [], "findings": []},
    )

    assert analysis["slo_breaches"][0]["phase"] == "stress"
    assert any(item["metric"] == "rps" and item["target"] == "p95_latency_ms" for item in analysis["correlations"])
    assert reasoning["mode"] == "bounded_react"
    assert reasoning["conclusion"]["classification"] == "load_induced_breakpoint"
    assert reasoning["trace"][0]["action"] == "inspect_slo_breaches"
