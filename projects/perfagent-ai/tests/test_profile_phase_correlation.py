from perfagent.analyzers.profile_phase_correlation import analyze_profile_phase_correlation


def test_profile_phase_correlation_maps_capture_window_to_phases_and_breach():
    aligned = [
        {"timestamp": "2026-06-14T10:00:00Z", "phase": "baseline", "p95_latency_ms": 200, "error_rate_percent": 0.1},
        {"timestamp": "2026-06-14T10:00:10Z", "phase": "stress", "p95_latency_ms": 520, "error_rate_percent": 0.3},
        {"timestamp": "2026-06-14T10:00:20Z", "phase": "stress", "p95_latency_ms": 880, "error_rate_percent": 2.2},
        {"timestamp": "2026-06-14T10:00:30Z", "phase": "recovery", "p95_latency_ms": 240, "error_rate_percent": 0.2},
    ]
    profiling = {
        "enabled": True,
        "auto_capture": {
            "capture_window": {
                "started_at": "2026-06-14T10:00:15Z",
                "ended_at": "2026-06-14T10:00:35Z",
                "duration_seconds": 20,
            },
            "profile_target": {"pid": "123", "container": "payments-api"},
            "artifacts": [
                {
                    "artifact_path": "raw/profiles/captured/perf.folded",
                    "type": "collapsed-stacks",
                    "summary": {
                        "top_functions": [
                            {"name": "postgresClient.query", "percent": 41.5, "samples": 83},
                        ]
                    },
                }
            ],
        },
    }

    result = analyze_profile_phase_correlation(
        profiling,
        aligned,
        features={"first_slo_breach_timestamp": "2026-06-14T10:00:20Z"},
        bucket_seconds=10,
    )

    assert result["enabled"] is True
    assert result["capture_windows"][0]["overlapped_phases"] == ["stress", "recovery"]
    assert result["capture_windows"][0]["breach_overlap"] is True
    assert result["capture_windows"][0]["target_pid"] == "123"
    assert result["artifact_correlations"][0]["artifact_path"] == "raw/profiles/captured/perf.folded"
    assert result["artifact_correlations"][0]["overlapped_phases"] == ["stress", "recovery"]
    assert result["artifact_correlations"][0]["top_functions"][0]["name"] == "postgresClient.query"
    assert result["warnings"] == []


def test_profile_phase_correlation_warns_without_capture_timestamps():
    result = analyze_profile_phase_correlation(
        {"enabled": True, "profiles": [{"artifact_path": "raw/profiles/cpu.pprof", "summary": {"top_functions": []}}]},
        [{"timestamp": "2026-06-14T10:00:00Z", "phase": "baseline"}],
        features={},
    )

    assert result["enabled"] is True
    assert result["artifact_correlations"][0]["overlap_confidence"] == "low"
    assert "capture window metadata missing" in result["warnings"][0]
