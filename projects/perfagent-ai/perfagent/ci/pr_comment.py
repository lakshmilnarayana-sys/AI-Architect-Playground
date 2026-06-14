from __future__ import annotations

from typing import Any


def format_pr_comment(summary: dict[str, Any], regression: dict[str, Any] | None = None) -> str:
    features = summary.get("features", {})
    bottleneck = summary.get("bottleneck_analysis", {})
    regression = regression or {"regression_detected": False, "findings": []}
    lines = [
        "## PerfAgent Performance Report",
        "",
        f"Service: `{summary.get('service_name', 'unknown')}`",
        f"Decision: `{summary.get('release_decision', 'UNKNOWN')}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Stable RPS | {features.get('stable_rps', 0)} |",
        f"| Peak RPS | {features.get('peak_rps', 0)} |",
        f"| Estimated capacity RPS | {features.get('estimated_capacity_rps', 'n/a')} |",
        f"| Breaking point RPS | {features.get('breaking_point_rps', 'n/a')} |",
        f"| Max p95 latency ms | {features.get('max_p95_latency_ms', 0)} |",
        f"| Max error rate % | {features.get('max_error_rate_percent', 0)} |",
        "",
        f"Bottleneck: `{bottleneck.get('bottleneck', 'unknown')}` ({bottleneck.get('confidence', 'unknown')} confidence)",
        "",
        f"Regression detected: `{bool(regression.get('regression_detected'))}`",
    ]
    findings = regression.get("findings") or []
    if findings:
        lines.append("")
        lines.append("Regression findings:")
        lines.extend(f"- {finding}" for finding in findings)
    if summary.get("report_html_path"):
        lines.append("")
        lines.append(f"HTML report: `{summary['report_html_path']}`")
    return "\n".join(lines) + "\n"
