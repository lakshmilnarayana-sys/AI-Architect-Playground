from perfagent.analyzers.features import extract_features


def test_extract_features_computes_slo_metrics_and_warn_decision():
    summary = {
        "metrics": {
            "http_reqs": {"count": 6000, "rate": 410.0},
            "http_req_duration": {"percentiles": {"p(95)": 920.0, "p(99)": 1200.0}},
            "http_req_failed": {"rate": 0.032},
            "vus": {"max": 50},
        }
    }
    aligned = [
        {"timestamp": "2026-06-13T10:00:00Z", "phase": "baseline", "rps": 200, "p95_latency_ms": 220, "error_rate_percent": 0.1},
        {"timestamp": "2026-06-13T10:05:00Z", "phase": "stress", "rps": 500, "p95_latency_ms": 920, "error_rate_percent": 3.2},
    ]

    features = extract_features(summary, aligned, slo_p95_ms=500, slo_error_rate_percent=1)

    assert features["stable_rps"] == 410.0
    assert features["max_p95_latency_ms"] == 920.0
    assert features["max_p99_latency_ms"] == 1200.0
    assert features["max_error_rate_percent"] == 3.2
    assert features["first_slo_breach_phase"] == "stress"
    assert features["release_decision"] == "WARN"


def test_extract_features_reads_k6_v2_values_and_marks_error_breach():
    summary = {
        "metrics": {
            "http_reqs": {"count": 14133, "rate": 100.29},
            "http_req_duration": {"p(95)": 27.5, "p(99)": 40.1},
            "http_req_failed": {"value": 1},
        }
    }

    features = extract_features(summary, [], slo_p95_ms=500, slo_error_rate_percent=1)

    assert features["max_p95_latency_ms"] == 27.5
    assert features["max_p99_latency_ms"] == 40.1
    assert features["max_error_rate_percent"] == 100.0
    assert features["release_decision"] == "WARN"


def test_extract_features_reports_capacity_and_breakpoint_from_slo_breach():
    summary = {
        "metrics": {
            "http_reqs": {"count": 9000, "rate": 420.0},
            "http_req_duration": {"p(95)": 780.0, "p(99)": 1100.0},
            "http_req_failed": {"value": 0.025},
        }
    }
    aligned = [
        {"timestamp": "2026-06-13T10:00:00Z", "phase": "baseline", "rps": 200, "p95_latency_ms": 260, "error_rate_percent": 0.2},
        {"timestamp": "2026-06-13T10:05:00Z", "phase": "stress", "rps": 500, "p95_latency_ms": 780, "error_rate_percent": 2.5},
        {"timestamp": "2026-06-13T10:06:00Z", "phase": "recovery", "rps": 50, "p95_latency_ms": 240, "error_rate_percent": 0.1},
    ]

    features = extract_features(summary, aligned, slo_p95_ms=500, slo_error_rate_percent=1)

    assert features["estimated_capacity_rps"] == 200.0
    assert features["breaking_point_rps"] == 500
    assert features["capacity_confidence"] == "medium"
    assert features["capacity_basis"] == "highest observed RPS before first SLO breach"
    assert features["headroom_rps"] == 300.0


def test_extract_features_reports_insufficient_capacity_evidence_without_aligned_rows():
    summary = {
        "metrics": {
            "http_reqs": {"count": 3000, "rate": 120.0},
            "http_req_duration": {"p(95)": 320.0, "p(99)": 480.0},
            "http_req_failed": {"value": 0.002},
        }
    }

    features = extract_features(summary, [], slo_p95_ms=500, slo_error_rate_percent=1)

    assert features["estimated_capacity_rps"] == 120.0
    assert features["breaking_point_rps"] is None
    assert features["capacity_confidence"] == "low"
    assert features["capacity_basis"] == "insufficient aligned time-series rows for capacity estimate"
    assert features["capacity_limit_reason"] == "insufficient_timeseries_rows"
    assert features["capacity_safe_phase"] is None
    assert features["capacity_stress_phase"] is None


def test_extract_features_sorts_rows_before_capacity_breakpoint_detection():
    summary = {
        "metrics": {
            "http_reqs": {"count": 9000, "rate": 420.0},
            "http_req_duration": {"p(95)": 780.0, "p(99)": 1100.0},
            "http_req_failed": {"value": 0.025},
        }
    }
    aligned = [
        {"timestamp": "2026-06-13T10:05:00Z", "phase": "capacity_probe_500", "rps": 500, "p95_latency_ms": 780, "error_rate_percent": 0.2},
        {"timestamp": "2026-06-13T10:00:00Z", "phase": "capacity_probe_200", "rps": 200, "p95_latency_ms": 260, "error_rate_percent": 0.2},
        {"timestamp": "2026-06-13T10:06:00Z", "phase": "recovery", "rps": 50, "p95_latency_ms": 240, "error_rate_percent": 0.1},
    ]

    features = extract_features(summary, aligned, slo_p95_ms=500, slo_error_rate_percent=1)

    assert features["estimated_capacity_rps"] == 200.0
    assert features["breaking_point_rps"] == 500
    assert features["first_slo_breach_phase"] == "capacity_probe_500"
    assert features["capacity_limit_phase"] == "capacity_probe_500"
    assert features["capacity_limit_reason"] == "latency_slo_breach"
    assert features["capacity_safe_phase"] == "capacity_probe_200"
    assert features["capacity_stress_phase"] == "capacity_probe_500"
