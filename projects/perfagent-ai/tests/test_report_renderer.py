from perfagent.generators.report_renderer import render_reports


def test_report_renderer_includes_capacity_and_profiling_sections(tmp_path):
    paths = render_reports(
        output_dir=tmp_path,
        service_name="payments-api",
        runtime="go",
        target_url="http://localhost:8080",
        strategy={"duration": "1m", "stages": []},
        contract_analysis={"endpoints": []},
        features={
            "release_decision": "WARN",
            "max_p95_latency_ms": 780,
            "slo_p95_latency_ms": 500,
            "max_error_rate_percent": 2.5,
            "slo_error_rate_percent": 1,
            "stable_rps": 420,
            "peak_rps": 500,
            "estimated_capacity_rps": 410,
            "breaking_point_rps": 500,
            "capacity_basis": "highest observed RPS before first SLO breach",
            "capacity_confidence": "medium",
            "first_slo_breach_phase": "stress",
        },
        bottleneck_analysis={"bottleneck": "dependency_or_unknown", "confidence": "medium", "evidence": [], "recommendations": []},
        profiling_artifacts={
            "artifacts": ["raw/profiles/cpu.pprof"],
            "profiles": [
                {
                    "artifact_path": "raw/profiles/cpu.pprof",
                    "source_path": "./cpu.pprof",
                    "type": "pprof",
                    "render_status": "not_rendered",
                    "warnings": ["Rendering is not implemented for pprof profiles yet."],
                }
            ],
        },
        service_resources={
            "cpu_allocation": "500m",
            "memory_allocation": "512Mi",
            "disk_allocation": "2Gi",
            "image_tag": "payments-api:v1.2.3",
        },
        aligned_timeseries=[
            {"timestamp": "2026-06-13T10:00:00Z", "phase": "baseline", "rps": 200, "p95_latency_ms": 260, "p99_latency_ms": 320, "error_rate_percent": 0.2, "virtual_users": 25},
            {"timestamp": "2026-06-13T10:00:10Z", "phase": "stress", "rps": 500, "p95_latency_ms": 780, "p99_latency_ms": 1100, "error_rate_percent": 2.5, "virtual_users": 100},
        ],
        timeseries_analysis={
            "row_count": 2,
            "metrics_available": ["rps", "p95_latency_ms", "error_rate_percent"],
            "missing_core_metrics": [],
            "slo_breaches": [{"timestamp": "2026-06-13T10:00:10Z", "phase": "stress"}],
            "correlations": [{"metric": "rps", "target": "p95_latency_ms", "correlation": 0.99, "strength": "strong"}],
            "recovery": {"status": "unknown"},
        },
        react_reasoning={
            "mode": "bounded_react",
            "trace": [{"step": 1, "thought": "inspect breach", "action": "inspect_slo_breaches", "observation": {"evidence": ["first breach in stress"]}}],
            "conclusion": {"classification": "load_induced_breakpoint", "confidence": "medium", "summary": "Load induced breakpoint.", "evidence": ["first breach in stress"]},
        },
    )

    report = paths["report_md_path"].read_text()
    assert "Estimated capacity RPS: 410" in report
    assert "Breaking point RPS: 500" in report
    assert "Capacity confidence: medium" in report
    assert "raw/profiles/cpu.pprof" in report
    assert "type=pprof" in report
    assert "render_status=not_rendered" in report
    assert "CPU allocation: 500m" in report
    assert "Image tag: payments-api:v1.2.3" in report
    assert "Autonomous Time-Series Reasoning" in report
    assert "load_induced_breakpoint" in report

    html = paths["report_html_path"].read_text()
    assert 'id="perfagent-data"' in html
    assert 'id="latency-rps-chart"' in html
    assert 'id="phase-filter"' in html
    assert 'id="timeseries-table"' in html
    assert 'id="service-resources"' in html
    assert 'id="chart-tooltip"' in html
    assert 'id="theme-toggle"' in html
    assert 'id="react-reasoning"' in html
    assert 'id="timeseries-analysis"' in html
    assert "function setTheme" in html
    assert "function renderReactReasoning" in html
    assert "Render status" in html
    assert "X-axis: time buckets" in html
    assert "Left Y-axis: p95 latency" in html
    assert "Right Y-axis: throughput" in html
    assert "function renderChart" in html
    assert "function renderTable" in html
    assert "2026-06-13T10:00:10Z" in html
