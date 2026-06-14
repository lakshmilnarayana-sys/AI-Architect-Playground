from perfagent.generators.trend_dashboard import render_trend_dashboard


def test_render_trend_dashboard_contains_axes_and_rows(tmp_path):
    output = tmp_path / "trends.html"
    render_trend_dashboard(
        [
            {
                "created_at": "2026-06-14T10:00:00Z",
                "run_id": "run-1",
                "service_name": "payments-api",
                "release_decision": "PASS",
                "stable_rps": 100,
                "max_p95_latency_ms": 200,
                "max_error_rate_percent": 0.1,
                "report_html_path": "report.html",
            }
        ],
        output,
    )

    html = output.read_text()
    assert "x-axis: run time/order" in html
    assert "p95 latency" in html
    assert "payments-api" in html
