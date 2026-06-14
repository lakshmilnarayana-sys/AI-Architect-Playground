from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from perfagent.core.artifacts import write_json


def render_reports(
    *,
    output_dir: Path,
    service_name: str,
    runtime: str,
    target_url: str,
    strategy: dict[str, Any],
    contract_analysis: dict[str, Any],
    features: dict[str, Any],
    bottleneck_analysis: dict[str, Any],
    profiling_artifacts: dict[str, Any] | None = None,
    service_resources: dict[str, Any] | None = None,
    dependency_analysis: dict[str, Any] | None = None,
    protocol_analysis: dict[str, Any] | None = None,
    ai_analysis: dict[str, Any] | None = None,
    traffic_profile: dict[str, Any] | None = None,
    aligned_timeseries: list[dict[str, Any]] | None = None,
    timeseries_analysis: dict[str, Any] | None = None,
    react_reasoning: dict[str, Any] | None = None,
) -> dict[str, Path]:
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown = _markdown(
        service_name,
        runtime,
        target_url,
        strategy,
        contract_analysis,
        features,
        bottleneck_analysis,
        profiling_artifacts or {},
        service_resources or {},
        dependency_analysis or {"dependencies": [], "findings": []},
        protocol_analysis or {"protocol_metrics": {}, "findings": [], "warnings": []},
        ai_analysis or {},
        traffic_profile or {},
        timeseries_analysis or {},
        react_reasoning or {},
    )
    md_path = reports_dir / "report.md"
    html_path = reports_dir / "report.html"
    summary_path = reports_dir / "summary.json"
    md_path.write_text(markdown)
    html_path.write_text(
        _interactive_html(
            service_name=service_name,
            runtime=runtime,
            target_url=target_url,
            strategy=strategy,
            contract_analysis=contract_analysis,
            features=features,
            bottleneck_analysis=bottleneck_analysis,
            profiling_artifacts=profiling_artifacts or {},
            service_resources=service_resources or {},
            dependency_analysis=dependency_analysis or {"dependencies": [], "findings": []},
            protocol_analysis=protocol_analysis or {"protocol_metrics": {}, "findings": [], "warnings": []},
            ai_analysis=ai_analysis or {},
            traffic_profile=traffic_profile or {},
            aligned_timeseries=aligned_timeseries or [],
            timeseries_analysis=timeseries_analysis or {},
            react_reasoning=react_reasoning or {},
        )
    )
    write_json(
        summary_path,
        {
            "service_name": service_name,
            "release_decision": features.get("release_decision", "UNKNOWN"),
            "features": features,
            "bottleneck_analysis": bottleneck_analysis,
            "profiling_artifacts": profiling_artifacts or {},
            "service_resources": service_resources or {},
            "dependency_analysis": dependency_analysis or {"dependencies": [], "findings": []},
            "protocol_analysis": protocol_analysis or {"protocol_metrics": {}, "findings": [], "warnings": []},
            "ai_analysis": ai_analysis or {},
            "traffic_profile": traffic_profile or {},
            "aligned_timeseries": aligned_timeseries or [],
            "timeseries_analysis": timeseries_analysis or {},
            "react_reasoning": react_reasoning or {},
        },
    )
    return {"report_md_path": md_path, "report_html_path": html_path, "summary_path": summary_path}


def _markdown(
    service_name: str,
    runtime: str,
    target_url: str,
    strategy: dict[str, Any],
    contract_analysis: dict[str, Any],
    features: dict[str, Any],
    bottleneck: dict[str, Any],
    profiling: dict[str, Any],
    service_resources: dict[str, Any],
    dependency_analysis: dict[str, Any],
    protocol_analysis: dict[str, Any],
    ai_analysis: dict[str, Any],
    traffic_profile: dict[str, Any],
    timeseries_analysis: dict[str, Any],
    react_reasoning: dict[str, Any],
) -> str:
    endpoints = contract_analysis.get("endpoints", [])
    evidence = "\n".join(f"- {item}" for item in bottleneck.get("evidence", [])) or "- No evidence available."
    recommendations = "\n".join(
        f"{index}. {item}" for index, item in enumerate(bottleneck.get("recommendations", []), start=1)
    ) or "1. Collect more metrics and re-run the test."
    profiles = _profile_lines(profiling)
    resources = _resource_lines(service_resources)
    dependencies = _dependency_lines(dependency_analysis)
    protocols = _protocol_lines(protocol_analysis)
    ai = _ai_lines(ai_analysis)
    traffic = _traffic_profile_lines(traffic_profile)
    react = _react_lines(react_reasoning)
    timeseries = _timeseries_lines(timeseries_analysis)
    return f"""# PerfAgent AI Report: {service_name}

## Executive Summary

Release decision: **{features.get("release_decision", "UNKNOWN")}**.
Max p95 latency was {features.get("max_p95_latency_ms", 0)} ms against an SLO of {features.get("slo_p95_latency_ms", 0)} ms. Max error rate was {features.get("max_error_rate_percent", 0)}% against an SLO of {features.get("slo_error_rate_percent", 0)}%.

## Service Under Test

- Service: {service_name}
- Runtime: {runtime}
- Target URL: {target_url}

## Service Under Test Resources

{resources}

## Test Strategy

- Duration: {strategy.get("duration", "unknown")}
- Stages: {strategy.get("stages", [])}

## Production Traffic Profile

{traffic}

## API Coverage

- Endpoints covered: {len(endpoints)}

## Results

- Stable RPS: {features.get("stable_rps", 0)}
- Peak RPS: {features.get("peak_rps", 0)}
- Estimated capacity RPS: {features.get("estimated_capacity_rps")}
- Breaking point RPS: {features.get("breaking_point_rps")}
- Capacity basis: {features.get("capacity_basis")}
- Capacity confidence: {features.get("capacity_confidence")}
- First SLO breach phase: {features.get("first_slo_breach_phase")}

## Bottleneck Analysis

- Bottleneck: {bottleneck.get("bottleneck", "unknown")}
- Confidence: {bottleneck.get("confidence", "unknown")}

## Dependency Analysis

{dependencies}

## Protocol Analysis

{protocols}

## Autonomous Time-Series Reasoning

{react}

## Time-Series Signal Analysis

{timeseries}

## AI Analysis

{ai}

## Evidence

{evidence}

## Recommendations

{recommendations}

## Profiling

{profiles}

## Release Decision

Decision: {features.get("release_decision", "UNKNOWN")}
"""


def _resource_lines(service_resources: dict[str, Any]) -> str:
    labels = [
        ("CPU allocation", "cpu_allocation"),
        ("Memory allocation", "memory_allocation"),
        ("Disk allocation", "disk_allocation"),
        ("Image tag", "image_tag"),
    ]
    return "\n".join(f"- {label}: {service_resources.get(key) or 'n/a'}" for label, key in labels)


def _profile_lines(profiling: dict[str, Any]) -> str:
    profiles = profiling.get("profiles", [])
    if profiles:
        lines = []
        for profile in profiles:
            warning_text = "; warnings=" + "; ".join(profile.get("warnings", [])) if profile.get("warnings") else ""
            lines.append(
                f"- {profile.get('artifact_path') or profile.get('source_path')}: "
                f"type={profile.get('type', 'unknown')}, render_status={profile.get('render_status', 'unknown')}{warning_text}"
            )
        return "\n".join(lines)
    return "\n".join(f"- {item}" for item in profiling.get("artifacts", [])) or "- No profiling artifacts attached."


def _dependency_lines(dependency_analysis: dict[str, Any]) -> str:
    dependencies = dependency_analysis.get("dependencies", [])
    findings = dependency_analysis.get("findings", [])
    if not dependencies:
        return "- No dependencies declared."
    lines = [
        f"- {item.get('name')}: type={item.get('type', 'unknown')}, role={item.get('role', 'downstream')}, criticality={item.get('criticality', 'medium')}"
        for item in dependencies
    ]
    if findings:
        lines.append("")
        lines.append("Findings:")
        lines.extend(
            f"- {item.get('dependency')} {item.get('metric')}={item.get('value')} exceeded {item.get('threshold', 'n/a')}"
            for item in findings
        )
    return "\n".join(lines)


def _protocol_lines(protocol_analysis: dict[str, Any]) -> str:
    metrics = protocol_analysis.get("protocol_metrics", {})
    browser_metrics = protocol_analysis.get("browser_metrics", {})
    findings = protocol_analysis.get("findings", [])
    warnings = protocol_analysis.get("warnings", [])
    if not metrics and not browser_metrics and not findings:
        return "\n".join(f"- Warning: {item}" for item in warnings) or "- No protocol-native metrics available."
    lines = [f"- {key}: {value}" for key, value in sorted(metrics.items())]
    lines.extend(f"- browser_{key}: {value}" for key, value in sorted(browser_metrics.items()))
    if findings:
        lines.append("")
        lines.append("Findings:")
        lines.extend(f"- {item.get('type')}: {item.get('evidence')}" for item in findings)
    return "\n".join(lines)


def _ai_lines(ai_analysis: dict[str, Any]) -> str:
    if not ai_analysis or not ai_analysis.get("enabled"):
        return f"- {ai_analysis.get('summary', 'AI analysis was not run.') if ai_analysis else 'AI analysis was not run.'}"
    recommendations = ai_analysis.get("recommendations", [])
    rec_lines = "\n".join(f"  {index}. {item}" for index, item in enumerate(recommendations, start=1))
    return "\n".join(
        [
            f"- Provider: {ai_analysis.get('provider', 'unknown')}",
            f"- Model: {ai_analysis.get('model', 'unknown')}",
            f"- Summary: {ai_analysis.get('summary', '')}",
            f"- Bottleneck: {ai_analysis.get('bottleneck', 'unknown')}",
            f"- Confidence: {ai_analysis.get('confidence', 'unknown')}",
            "Recommendations:",
            rec_lines or "  1. No AI recommendations returned.",
        ]
    )


def _traffic_profile_lines(traffic_profile: dict[str, Any]) -> str:
    if not traffic_profile or not traffic_profile.get("enabled"):
        return "- No production traffic profile was used."
    endpoint_lines = "\n".join(
        f"- {item.get('path')}: weight={item.get('weight')}, observed_rps={item.get('observed_rps')}"
        for item in traffic_profile.get("endpoint_mix", [])
    )
    return "\n".join(
        [
            f"- Source: {traffic_profile.get('source')}",
            f"- Production-like RPS: {traffic_profile.get('production_like_rps')}",
            f"- Peak RPS: {traffic_profile.get('peak_rps')}",
            "Endpoint mix:",
            endpoint_lines or "- No endpoint mix available.",
        ]
    )


def _react_lines(react_reasoning: dict[str, Any]) -> str:
    conclusion = react_reasoning.get("conclusion", {})
    trace = react_reasoning.get("trace", [])
    lines = [
        f"- Mode: {react_reasoning.get('mode', 'n/a')}",
        f"- Classification: {conclusion.get('classification', 'unknown')}",
        f"- Confidence: {conclusion.get('confidence', 'unknown')}",
        f"- Summary: {conclusion.get('summary', 'No autonomous reasoning summary available.')}",
    ]
    if trace:
        lines.append("Trace:")
        lines.extend(
            f"- Step {item.get('step')}: {item.get('action')} -> {', '.join(item.get('observation', {}).get('evidence', [])[:2])}"
            for item in trace
        )
    return "\n".join(lines)


def _timeseries_lines(timeseries_analysis: dict[str, Any]) -> str:
    if not timeseries_analysis:
        return "- No time-series analysis available."
    correlations = timeseries_analysis.get("correlations", [])
    breaches = timeseries_analysis.get("slo_breaches", [])
    missing = timeseries_analysis.get("missing_core_metrics", [])
    lines = [
        f"- Rows analyzed: {timeseries_analysis.get('row_count', 0)}",
        f"- Metrics available: {', '.join(timeseries_analysis.get('metrics_available', [])) or 'none'}",
        f"- SLO breach windows: {len(breaches)}",
        f"- Missing core metrics: {', '.join(missing) if missing else 'none'}",
    ]
    if correlations:
        lines.append("Strong correlations:")
        lines.extend(
            f"- {item.get('metric')} vs {item.get('target')}: {item.get('correlation')} ({item.get('strength')})"
            for item in correlations[:5]
        )
    return "\n".join(lines)


def _interactive_html(
    *,
    service_name: str,
    runtime: str,
    target_url: str,
    strategy: dict[str, Any],
    contract_analysis: dict[str, Any],
    features: dict[str, Any],
    bottleneck_analysis: dict[str, Any],
    profiling_artifacts: dict[str, Any],
    service_resources: dict[str, Any],
    dependency_analysis: dict[str, Any],
    protocol_analysis: dict[str, Any],
    ai_analysis: dict[str, Any],
    traffic_profile: dict[str, Any],
    aligned_timeseries: list[dict[str, Any]],
    timeseries_analysis: dict[str, Any],
    react_reasoning: dict[str, Any],
) -> str:
    payload = {
        "serviceName": service_name,
        "runtime": runtime,
        "targetUrl": target_url,
        "strategy": strategy,
        "apiCoverage": {"endpointCount": len(contract_analysis.get("endpoints", []))},
        "features": features,
        "bottleneck": bottleneck_analysis,
        "profiling": profiling_artifacts,
        "serviceResources": service_resources,
        "dependencyAnalysis": dependency_analysis,
        "protocolAnalysis": protocol_analysis,
        "aiAnalysis": ai_analysis,
        "trafficProfile": traffic_profile,
        "timeseries": aligned_timeseries,
        "timeseriesAnalysis": timeseries_analysis,
        "reactReasoning": react_reasoning,
    }
    data = html.escape(json.dumps(payload, sort_keys=True), quote=False)
    title = html.escape(f"PerfAgent Report: {service_name}")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --bg: #f5f7fa;
      --surface: #ffffff;
      --surface-muted: #f8fafc;
      --text: #17202a;
      --muted: #5d6b7c;
      --header-bg: #132238;
      --header-text: #ffffff;
      --border: #d8dee8;
      --axis: #9aa6b2;
      --grid-line: #edf1f5;
      --latency: #b42318;
      --rps: #1b5e3b;
      --breakpoint: #8a5a00;
      --tooltip-shadow: rgba(18, 34, 56, .16);
    }}
    html[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #0f141b;
      --surface: #171e27;
      --surface-muted: #202936;
      --text: #e8edf3;
      --muted: #a7b3c2;
      --header-bg: #0a0f16;
      --header-text: #f8fafc;
      --border: #344052;
      --axis: #7f8b9c;
      --grid-line: #283241;
      --latency: #ff6b5f;
      --rps: #63d08b;
      --breakpoint: #f6c453;
      --tooltip-shadow: rgba(0, 0, 0, .38);
    }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    header {{ background: var(--header-bg); color: var(--header-text); padding: 24px clamp(16px, 4vw, 48px); }}
    .header-row {{ display: flex; align-items: flex-start; gap: 16px; justify-content: space-between; }}
    main {{ padding: 24px clamp(16px, 4vw, 48px); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }}
    .subtle {{ color: #d8e0eb; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(4, minmax(160px, 1fr)); margin-bottom: 18px; }}
    .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
    .kpi span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .kpi strong {{ display: block; margin-top: 8px; font-size: 24px; }}
    .decision {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; font-weight: 800; background: #e6f3ed; color: #145c3a; }}
    .decision.WARN {{ background: #fff3d6; color: #8a5a00; }}
    .decision.BLOCK, .decision.UNKNOWN {{ background: #fde3df; color: #982b1f; }}
    .chart-wrap {{ min-height: 390px; position: relative; }}
    svg {{ width: 100%; height: 350px; display: block; }}
    .chart-note {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
    .chart-tooltip {{ position: absolute; display: none; pointer-events: none; min-width: 210px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text); box-shadow: 0 10px 24px var(--tooltip-shadow); padding: 10px; font-size: 12px; z-index: 3; }}
    .chart-tooltip strong {{ display: block; margin-bottom: 6px; }}
    .controls {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
    select, button {{ border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text); padding: 8px 10px; font-size: 14px; }}
    button {{ cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 9px 8px; text-align: left; }}
    th {{ cursor: pointer; color: var(--muted); background: var(--surface-muted); position: sticky; top: 0; }}
    .two-col {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, .55fr); gap: 16px; }}
    ul {{ margin: 0; padding-left: 20px; }}
    @media (max-width: 920px) {{ .grid, .two-col {{ grid-template-columns: 1fr; }} .header-row {{ flex-direction: column; }} }}
  </style>
</head>
<body>
  <script id="perfagent-data" type="application/json">{data}</script>
  <header>
    <div class="header-row">
      <div>
        <h1>{title}</h1>
        <div class="subtle" id="service-meta"></div>
      </div>
      <button id="theme-toggle" type="button" aria-label="Switch dark and light mode">Dark mode</button>
    </div>
  </header>
  <main>
    <section class="grid" id="kpi-grid"></section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Service Under Test Resources</h2>
      <div id="service-resources"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Dependency Analysis</h2>
      <div id="dependency-analysis"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Protocol Analysis</h2>
      <div id="protocol-analysis"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Autonomous Time-Series Reasoning</h2>
      <div id="react-reasoning"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Time-Series Signal Analysis</h2>
      <div id="timeseries-analysis"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>AI Analysis</h2>
      <div id="ai-analysis"></div>
    </section>
    <section class="panel" style="margin-bottom:16px">
      <h2>Production Traffic Profile</h2>
      <div id="traffic-profile"></div>
    </section>
    <section class="two-col">
      <div class="panel chart-wrap">
        <h2>Latency And Throughput Timeline</h2>
        <svg id="latency-rps-chart" role="img" aria-label="Latency and RPS chart"></svg>
        <div id="chart-tooltip" class="chart-tooltip"></div>
        <div class="chart-note">X-axis: time buckets. Left Y-axis: p95 latency in milliseconds. Right Y-axis: throughput in requests per second.</div>
      </div>
      <div class="panel">
        <h2>Bottleneck Analysis</h2>
        <div id="bottleneck"></div>
      </div>
    </section>
    <section class="panel" style="margin-top:16px">
      <div class="controls">
        <h2 style="margin-right:auto">Aligned Time-Series</h2>
        <label for="phase-filter">Phase</label>
        <select id="phase-filter"></select>
      </div>
      <div style="overflow:auto; max-height:420px">
        <table id="timeseries-table"></table>
      </div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Profiling Artifacts</h2>
      <div id="profiles"></div>
    </section>
  </main>
  <script>
    const data = JSON.parse(document.getElementById('perfagent-data').textContent);
    let sortKey = 'timestamp';
    let sortAsc = true;

    function themeColors() {{
      const styles = getComputedStyle(document.documentElement);
      return {{
        surface: styles.getPropertyValue('--surface').trim(),
        text: styles.getPropertyValue('--text').trim(),
        muted: styles.getPropertyValue('--muted').trim(),
        axis: styles.getPropertyValue('--axis').trim(),
        grid: styles.getPropertyValue('--grid-line').trim(),
        latency: styles.getPropertyValue('--latency').trim(),
        rps: styles.getPropertyValue('--rps').trim(),
        breakpoint: styles.getPropertyValue('--breakpoint').trim()
      }};
    }}

    function setTheme(theme) {{
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('perfagent-theme', theme);
      document.getElementById('theme-toggle').textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
      renderChart();
    }}

    function initTheme() {{
      const saved = localStorage.getItem('perfagent-theme');
      const preferred = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      setTheme(saved || preferred);
      document.getElementById('theme-toggle').addEventListener('click', () => {{
        setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
      }});
    }}

    function fmt(value, suffix = '') {{
      if (value === null || value === undefined || value === '') return 'n/a';
      if (typeof value === 'number') return `${{Math.round(value * 100) / 100}}${{suffix}}`;
      return `${{value}}${{suffix}}`;
    }}

    function renderMeta() {{
      document.getElementById('service-meta').textContent = `${{data.runtime}} | ${{data.targetUrl}} | ${{data.apiCoverage.endpointCount}} endpoints`;
    }}

    function renderKpis() {{
      const f = data.features;
      const items = [
        ['Decision', `<span class="decision ${{f.release_decision}}">${{f.release_decision || 'UNKNOWN'}}</span>`],
        ['Estimated capacity', fmt(f.estimated_capacity_rps, ' RPS')],
        ['Breaking point', fmt(f.breaking_point_rps, ' RPS')],
        ['Max p95', fmt(f.max_p95_latency_ms, ' ms')],
        ['Max error', fmt(f.max_error_rate_percent, '%')],
        ['Stable RPS', fmt(f.stable_rps)],
        ['Peak RPS', fmt(f.peak_rps)],
        ['Confidence', fmt(f.capacity_confidence)]
      ];
      document.getElementById('kpi-grid').innerHTML = items.map(([label, value]) => `<div class="panel kpi"><span>${{label}}</span><strong>${{value}}</strong></div>`).join('');
    }}

    function renderBottleneck() {{
      const b = data.bottleneck || {{}};
      const evidence = (b.evidence || []).map(item => `<li>${{item}}</li>`).join('') || '<li>No evidence available</li>';
      const recs = (b.recommendations || []).map(item => `<li>${{item}}</li>`).join('') || '<li>Collect more metrics and re-run.</li>';
      document.getElementById('bottleneck').innerHTML = `<p><strong>${{b.bottleneck || 'unknown'}}</strong> (${{b.confidence || 'unknown'}} confidence)</p><h3>Evidence</h3><ul>${{evidence}}</ul><h3>Recommendations</h3><ul>${{recs}}</ul>`;
    }}

    function renderServiceResources() {{
      const resources = data.serviceResources || {{}};
      const items = [
        ['CPU allocation', resources.cpu_allocation],
        ['Memory allocation', resources.memory_allocation],
        ['Disk allocation', resources.disk_allocation],
        ['Image tag', resources.image_tag]
      ];
      document.getElementById('service-resources').innerHTML = `<table><tbody>${{items.map(([label, value]) => `<tr><th>${{label}}</th><td>${{fmt(value)}}</td></tr>`).join('')}}</tbody></table>`;
    }}

    function renderDependencyAnalysis() {{
      const analysis = data.dependencyAnalysis || {{}};
      const dependencies = analysis.dependencies || [];
      const findings = analysis.findings || [];
      if (!dependencies.length) {{
        document.getElementById('dependency-analysis').innerHTML = '<p>No dependencies declared.</p>';
        return;
      }}
      const dependencyRows = dependencies.map(item => `<tr><td>${{fmt(item.name)}}</td><td>${{fmt(item.type)}}</td><td>${{fmt(item.role)}}</td><td>${{fmt(item.criticality)}}</td></tr>`).join('');
      const findingRows = findings.map(item => `<tr><td>${{fmt(item.dependency)}}</td><td>${{fmt(item.metric)}}</td><td>${{fmt(item.value)}}</td><td>${{fmt(item.threshold)}}</td></tr>`).join('');
      const findingsTable = findings.length ? `<h3>Findings</h3><table><thead><tr><th>Dependency</th><th>Metric</th><th>Observed</th><th>Threshold</th></tr></thead><tbody>${{findingRows}}</tbody></table>` : '<p>No dependency thresholds breached.</p>';
      document.getElementById('dependency-analysis').innerHTML = `<table><thead><tr><th>Name</th><th>Type</th><th>Role</th><th>Criticality</th></tr></thead><tbody>${{dependencyRows}}</tbody></table>${{findingsTable}}`;
    }}

    function renderProtocolAnalysis() {{
      const analysis = data.protocolAnalysis || {{}};
      const metrics = analysis.protocol_metrics || {{}};
      const browserMetrics = analysis.browser_metrics || {{}};
      const findings = analysis.findings || [];
      const warnings = analysis.warnings || [];
      const allMetrics = {{...metrics, ...Object.fromEntries(Object.entries(browserMetrics).map(([key, value]) => [`browser_${{key}}`, value]))}};
      const metricRows = Object.entries(allMetrics).map(([key, value]) => `<tr><td>${{fmt(key)}}</td><td>${{fmt(typeof value === 'object' ? JSON.stringify(value) : value)}}</td></tr>`).join('');
      const findingRows = findings.map(item => `<tr><td>${{fmt(item.type)}}</td><td>${{fmt(item.severity)}}</td><td>${{fmt(item.evidence)}}</td></tr>`).join('');
      const warningRows = warnings.map(item => `<li>${{fmt(item)}}</li>`).join('');
      document.getElementById('protocol-analysis').innerHTML = `
        <h3>Protocol Metrics</h3>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>${{metricRows || '<tr><td colspan="2">No protocol-native metrics available.</td></tr>'}}</tbody></table>
        <h3>Protocol Findings</h3>
        <table><thead><tr><th>Type</th><th>Severity</th><th>Evidence</th></tr></thead><tbody>${{findingRows || '<tr><td colspan="3">No protocol findings detected.</td></tr>'}}</tbody></table>
        ${{warningRows ? `<h3>Warnings</h3><ul>${{warningRows}}</ul>` : ''}}
      `;
    }}

    function renderReactReasoning() {{
      const reasoning = data.reactReasoning || {{}};
      const conclusion = reasoning.conclusion || {{}};
      const evidence = (conclusion.evidence || []).map(item => `<li>${{fmt(item)}}</li>`).join('');
      const traceRows = (reasoning.trace || []).map(item => {{
        const observed = ((item.observation || {{}}).evidence || []).slice(0, 3).map(value => `<li>${{fmt(value)}}</li>`).join('');
        return `<tr><td>${{fmt(item.step)}}</td><td>${{fmt(item.thought)}}</td><td>${{fmt(item.action)}}</td><td><ul>${{observed || '<li>n/a</li>'}}</ul></td></tr>`;
      }}).join('');
      document.getElementById('react-reasoning').innerHTML = `
        <table><tbody>
          <tr><th>Mode</th><td>${{fmt(reasoning.mode)}}</td></tr>
          <tr><th>Classification</th><td>${{fmt(conclusion.classification)}}</td></tr>
          <tr><th>Confidence</th><td>${{fmt(conclusion.confidence)}}</td></tr>
          <tr><th>Summary</th><td>${{fmt(conclusion.summary)}}</td></tr>
          <tr><th>Estimated capacity</th><td>${{fmt(conclusion.estimated_capacity_rps, ' RPS')}}</td></tr>
          <tr><th>Breakpoint</th><td>${{fmt(conclusion.breaking_point_rps, ' RPS')}}</td></tr>
        </tbody></table>
        <h3>Conclusion Evidence</h3><ul>${{evidence || '<li>No reasoning evidence available.</li>'}}</ul>
        <h3>Reasoning Trace</h3>
        <table><thead><tr><th>Step</th><th>Thought</th><th>Action</th><th>Observation</th></tr></thead><tbody>${{traceRows || '<tr><td colspan="4">No trace available.</td></tr>'}}</tbody></table>
      `;
    }}

    function renderTimeseriesAnalysis() {{
      const analysis = data.timeseriesAnalysis || {{}};
      const correlations = (analysis.correlations || []).slice(0, 8).map(item => `<tr><td>${{fmt(item.metric)}}</td><td>${{fmt(item.target)}}</td><td>${{fmt(item.correlation)}}</td><td>${{fmt(item.strength)}}</td></tr>`).join('');
      const breaches = (analysis.slo_breaches || []).slice(0, 8).map(item => `<tr><td>${{fmt(item.timestamp)}}</td><td>${{fmt(item.phase)}}</td><td>${{fmt(item.rps)}}</td><td>${{fmt(item.p95_latency_ms, ' ms')}}</td><td>${{fmt(item.error_rate_percent, '%')}}</td><td>${{fmt((item.reasons || []).join(', '))}}</td></tr>`).join('');
      const missing = (analysis.missing_core_metrics || []).join(', ') || 'none';
      document.getElementById('timeseries-analysis').innerHTML = `
        <table><tbody>
          <tr><th>Rows analyzed</th><td>${{fmt(analysis.row_count)}}</td></tr>
          <tr><th>Metrics available</th><td>${{fmt((analysis.metrics_available || []).join(', '))}}</td></tr>
          <tr><th>Missing core metrics</th><td>${{fmt(missing)}}</td></tr>
          <tr><th>Recovery</th><td>${{fmt((analysis.recovery || {{}}).status)}}</td></tr>
        </tbody></table>
        <h3>SLO Breach Windows</h3>
        <table><thead><tr><th>Timestamp</th><th>Phase</th><th>RPS</th><th>p95</th><th>Error</th><th>Reasons</th></tr></thead><tbody>${{breaches || '<tr><td colspan="6">No SLO breach windows detected.</td></tr>'}}</tbody></table>
        <h3>Strong Correlations</h3>
        <table><thead><tr><th>Metric</th><th>Target</th><th>Correlation</th><th>Strength</th></tr></thead><tbody>${{correlations || '<tr><td colspan="4">No strong correlations detected.</td></tr>'}}</tbody></table>
      `;
    }}

    function renderAiAnalysis() {{
      const ai = data.aiAnalysis || {{}};
      const recommendations = (ai.recommendations || []).map(item => `<li>${{item}}</li>`).join('');
      const evidence = (ai.evidence || []).map(item => `<li>${{item}}</li>`).join('');
      document.getElementById('ai-analysis').innerHTML = ai.enabled
        ? `<p><strong>${{fmt(ai.provider)}} / ${{fmt(ai.model)}}</strong></p><p>${{fmt(ai.summary)}}</p><table><tbody><tr><th>Bottleneck</th><td>${{fmt(ai.bottleneck)}}</td></tr><tr><th>Confidence</th><td>${{fmt(ai.confidence)}}</td></tr></tbody></table><h3>AI Evidence</h3><ul>${{evidence || '<li>No AI evidence returned.</li>'}}</ul><h3>AI Recommendations</h3><ul>${{recommendations || '<li>No AI recommendations returned.</li>'}}</ul>`
        : `<p>${{fmt(ai.summary || 'AI analysis was not run.')}}</p>`;
    }}

    function renderTrafficProfile() {{
      const profile = data.trafficProfile || {{}};
      if (!profile.enabled) {{
        document.getElementById('traffic-profile').innerHTML = '<p>No production traffic profile was used.</p>';
        return;
      }}
      const rows = (profile.endpoint_mix || []).map(item => `<tr><td>${{fmt(item.path)}}</td><td>${{fmt(item.weight)}}</td><td>${{fmt(item.observed_rps)}}</td></tr>`).join('');
      document.getElementById('traffic-profile').innerHTML = `<table><tbody><tr><th>Source</th><td>${{fmt(profile.source)}}</td></tr><tr><th>Production-like RPS</th><td>${{fmt(profile.production_like_rps)}}</td></tr><tr><th>Peak RPS</th><td>${{fmt(profile.peak_rps)}}</td></tr></tbody></table><h3>Endpoint Mix</h3><table><thead><tr><th>Path</th><th>Weight</th><th>Observed RPS</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function filteredRows() {{
      const phase = document.getElementById('phase-filter').value;
      const rows = phase === 'all' ? data.timeseries : data.timeseries.filter(row => row.phase === phase);
      return [...rows].sort((a, b) => {{
        const av = a[sortKey] ?? '';
        const bv = b[sortKey] ?? '';
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      }});
    }}

    function renderPhaseFilter() {{
      const phases = ['all', ...new Set(data.timeseries.map(row => row.phase || 'unknown'))];
      document.getElementById('phase-filter').innerHTML = phases.map(phase => `<option value="${{phase}}">${{phase}}</option>`).join('');
      document.getElementById('phase-filter').addEventListener('change', () => {{ renderChart(); renderTable(); }});
    }}

    function renderChart() {{
      const rows = filteredRows();
      const svg = document.getElementById('latency-rps-chart');
      const tooltip = document.getElementById('chart-tooltip');
      const colors = themeColors();
      const width = 980, height = 350;
      const margin = {{ top: 28, right: 78, bottom: 72, left: 74 }};
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      if (!rows.length) {{
        svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
        svg.innerHTML = `<text x="24" y="48" fill="${{colors.muted}}">No aligned time-series data available.</text>`;
        return;
      }}
      const maxLatency = Math.max(1, ...rows.map(row => Number(row.p95_latency_ms || 0)));
      const maxRps = Math.max(1, ...rows.map(row => Number(row.rps || 0)));
      const latencyTop = Math.ceil(maxLatency * 1.15);
      const rpsTop = Math.ceil(maxRps * 1.15);
      const x = index => margin.left + (rows.length <= 1 ? plotWidth / 2 : index * (plotWidth / (rows.length - 1)));
      const yLatency = value => margin.top + plotHeight - (Number(value || 0) / latencyTop) * plotHeight;
      const yRps = value => margin.top + plotHeight - (Number(value || 0) / rpsTop) * plotHeight;
      const line = (key, yFn) => rows.map((row, index) => `${{index === 0 ? 'M' : 'L'}}${{x(index)}},${{yFn(row[key])}}`).join(' ');
      const breach = rows.findIndex(row => row.phase === data.features.capacity_limit_phase || row.rps === data.features.breaking_point_rps);
      const yTicks = [0, .25, .5, .75, 1];
      const xTickIndexes = rows.length <= 6 ? rows.map((_, index) => index) : [0, Math.floor(rows.length * .25), Math.floor(rows.length * .5), Math.floor(rows.length * .75), rows.length - 1];
      const formatTime = value => {{
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString().slice(11, 19);
      }};
      const latencyTicks = yTicks.map(ratio => {{
        const y = margin.top + plotHeight - ratio * plotHeight;
        const value = Math.round(ratio * latencyTop);
        return `<line x1="${{margin.left}}" y1="${{y}}" x2="${{width - margin.right}}" y2="${{y}}" stroke="${{colors.grid}}"></line><text x="${{margin.left - 10}}" y="${{y + 4}}" text-anchor="end" fill="${{colors.muted}}" font-size="11">${{value}}</text>`;
      }}).join('');
      const rpsTicks = yTicks.map(ratio => {{
        const y = margin.top + plotHeight - ratio * plotHeight;
        const value = Math.round(ratio * rpsTop);
        return `<text x="${{width - margin.right + 10}}" y="${{y + 4}}" fill="${{colors.muted}}" font-size="11">${{value}}</text>`;
      }}).join('');
      const xTicks = xTickIndexes.map(index => {{
        const xx = x(index);
        return `<line x1="${{xx}}" y1="${{margin.top + plotHeight}}" x2="${{xx}}" y2="${{margin.top + plotHeight + 6}}" stroke="${{colors.axis}}"></line><text x="${{xx}}" y="${{height - 40}}" text-anchor="middle" fill="${{colors.muted}}" font-size="11">${{formatTime(rows[index].timestamp || '')}}</text><text x="${{xx}}" y="${{height - 24}}" text-anchor="middle" fill="${{colors.muted}}" font-size="10">${{rows[index].phase || ''}}</text>`;
      }}).join('');
      const points = rows.map((row, index) => {{
        const cx = x(index);
        return `<circle class="chart-point" data-index="${{index}}" data-series="latency" cx="${{cx}}" cy="${{yLatency(row.p95_latency_ms)}}" r="4" fill="${{colors.latency}}" stroke="${{colors.surface}}" stroke-width="1.5"></circle><circle class="chart-point" data-index="${{index}}" data-series="rps" cx="${{cx}}" cy="${{yRps(row.rps)}}" r="4" fill="${{colors.rps}}" stroke="${{colors.surface}}" stroke-width="1.5"></circle><rect class="chart-hit" data-index="${{index}}" x="${{cx - Math.max(8, plotWidth / Math.max(rows.length, 1) / 2)}}" y="${{margin.top}}" width="${{Math.max(16, plotWidth / Math.max(rows.length, 1))}}" height="${{plotHeight}}" fill="transparent"></rect>`;
      }}).join('');
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `
        <rect x="0" y="0" width="${{width}}" height="${{height}}" fill="${{colors.surface}}"></rect>
        ${{latencyTicks}}
        <line x1="${{margin.left}}" y1="${{margin.top + plotHeight}}" x2="${{width - margin.right}}" y2="${{margin.top + plotHeight}}" stroke="${{colors.axis}}"></line>
        <line x1="${{margin.left}}" y1="${{margin.top}}" x2="${{margin.left}}" y2="${{margin.top + plotHeight}}" stroke="${{colors.axis}}"></line>
        <line x1="${{width - margin.right}}" y1="${{margin.top}}" x2="${{width - margin.right}}" y2="${{margin.top + plotHeight}}" stroke="${{colors.axis}}"></line>
        ${{rpsTicks}}
        ${{xTicks}}
        <path d="${{line('p95_latency_ms', yLatency)}}" fill="none" stroke="${{colors.latency}}" stroke-width="3"></path>
        <path d="${{line('rps', yRps)}}" fill="none" stroke="${{colors.rps}}" stroke-width="3"></path>
        ${{breach >= 0 ? `<line x1="${{x(breach)}}" y1="${{margin.top}}" x2="${{x(breach)}}" y2="${{margin.top + plotHeight}}" stroke="${{colors.breakpoint}}" stroke-dasharray="5 5"></line><text x="${{x(breach) + 8}}" y="${{margin.top + 14}}" fill="${{colors.breakpoint}}" font-size="11">breakpoint</text>` : ''}}
        ${{points}}
        <text x="${{margin.left}}" y="16" fill="${{colors.latency}}" font-size="12" font-weight="700">p95 latency (ms)</text>
        <text x="${{width - margin.right}}" y="16" text-anchor="end" fill="${{colors.rps}}" font-size="12" font-weight="700">RPS</text>
        <text x="${{width / 2}}" y="${{height - 4}}" text-anchor="middle" fill="${{colors.text}}" font-size="12">X-axis: time buckets by phase</text>
        <text x="16" y="${{margin.top + plotHeight / 2}}" transform="rotate(-90 16 ${{margin.top + plotHeight / 2}})" text-anchor="middle" fill="${{colors.text}}" font-size="12">Left Y-axis: p95 latency (ms)</text>
        <text x="${{width - 16}}" y="${{margin.top + plotHeight / 2}}" transform="rotate(90 ${{width - 16}} ${{margin.top + plotHeight / 2}})" text-anchor="middle" fill="${{colors.text}}" font-size="12">Right Y-axis: throughput (RPS)</text>
      `;
      svg.querySelectorAll('.chart-hit, .chart-point').forEach(node => {{
        node.addEventListener('mousemove', event => {{
          const row = rows[Number(node.dataset.index)];
          tooltip.style.display = 'block';
          tooltip.style.left = `${{event.offsetX + 16}}px`;
          tooltip.style.top = `${{event.offsetY + 18}}px`;
          tooltip.innerHTML = `<strong>${{row.timestamp || 'time bucket'}}</strong><div>Phase: ${{row.phase || 'unknown'}}</div><div>p95 latency: ${{fmt(row.p95_latency_ms, ' ms')}}</div><div>p99 latency: ${{fmt(row.p99_latency_ms, ' ms')}}</div><div>RPS: ${{fmt(row.rps)}}</div><div>Error rate: ${{fmt(row.error_rate_percent, '%')}}</div><div>VUs: ${{fmt(row.virtual_users)}}</div>`;
        }});
        node.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});
      }});
    }}

    function renderTable() {{
      const columns = ['timestamp', 'phase', 'rps', 'p95_latency_ms', 'p99_latency_ms', 'error_rate_percent', 'virtual_users'];
      const rows = filteredRows();
      const header = `<thead><tr>${{columns.map(col => `<th data-key="${{col}}">${{col}}</th>`).join('')}}</tr></thead>`;
      const body = `<tbody>${{rows.map(row => `<tr>${{columns.map(col => `<td>${{fmt(row[col])}}</td>`).join('')}}</tr>`).join('')}}</tbody>`;
      const table = document.getElementById('timeseries-table');
      table.innerHTML = header + body;
      table.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {{
        const key = th.dataset.key;
        sortAsc = sortKey === key ? !sortAsc : true;
        sortKey = key;
        renderTable();
      }}));
    }}

    function renderProfiles() {{
      const structuredProfiles = data.profiling.profiles || [];
      if (structuredProfiles.length) {{
        const rows = structuredProfiles.map(item => {{
          const warnings = (item.warnings || []).join('; ') || 'none';
          return `<tr><td>${{fmt(item.artifact_path || item.source_path)}}</td><td>${{fmt(item.type)}}</td><td>${{fmt(item.render_status)}}</td><td>${{fmt(warnings)}}</td></tr>`;
        }}).join('');
        document.getElementById('profiles').innerHTML = `<table><thead><tr><th>Artifact</th><th>Type</th><th>Render status</th><th>Warnings</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        return;
      }}
      const profiles = data.profiling.artifacts || [];
      document.getElementById('profiles').innerHTML = profiles.length ? `<ul>${{profiles.map(item => `<li>${{item}}</li>`).join('')}}</ul>` : '<p>No profiling artifacts attached.</p>';
    }}

    renderMeta();
    renderKpis();
    renderServiceResources();
    renderDependencyAnalysis();
    renderProtocolAnalysis();
    renderReactReasoning();
    renderTimeseriesAnalysis();
    renderAiAnalysis();
    renderTrafficProfile();
    renderBottleneck();
    renderPhaseFilter();
    initTheme();
    renderTable();
    renderProfiles();
  </script>
</body>
</html>
"""
