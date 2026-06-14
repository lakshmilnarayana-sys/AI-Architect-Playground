from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_trend_dashboard(runs: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "created_at": run.get("created_at"),
            "run_id": run.get("run_id"),
            "service_name": run.get("service_name"),
            "release_decision": run.get("release_decision"),
            "stable_rps": run.get("stable_rps"),
            "max_p95_latency_ms": run.get("max_p95_latency_ms"),
            "max_error_rate_percent": run.get("max_error_rate_percent"),
            "report_html_path": run.get("report_html_path"),
        }
        for run in reversed(runs)
    ]
    payload = json.dumps(rows)
    output_path.write_text(
        f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>PerfAgent Trend Dashboard</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Inter, system-ui, sans-serif; }}
    body {{ margin: 0; padding: 24px; background: Canvas; color: CanvasText; }}
    h1 {{ margin: 0 0 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 8px; padding: 12px; }}
    svg {{ width: 100%; height: 320px; border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent); padding: 8px; text-align: left; }}
  </style>
</head>
<body>
  <h1>PerfAgent Trend Dashboard</h1>
  <div class=\"grid\" id=\"cards\"></div>
  <svg id=\"chart\" role=\"img\" aria-label=\"Trend chart with p95 latency and stable RPS over time\"></svg>
  <table>
    <thead><tr><th>Created</th><th>Service</th><th>Decision</th><th>p95 ms</th><th>Stable RPS</th><th>Error %</th><th>Report</th></tr></thead>
    <tbody id=\"rows\"></tbody>
  </table>
  <script>
    const runs = {payload};
    const latest = runs[runs.length - 1] || {{}};
    const cards = [
      ['Runs', runs.length],
      ['Latest decision', latest.release_decision || 'UNKNOWN'],
      ['Latest p95 ms', latest.max_p95_latency_ms ?? 0],
      ['Latest stable RPS', latest.stable_rps ?? 0],
    ];
    document.getElementById('cards').innerHTML = cards.map(([k,v]) => `<div class=\"card\"><strong>${{k}}</strong><br>${{v}}</div>`).join('');
    document.getElementById('rows').innerHTML = runs.map(r => `<tr><td>${{r.created_at || ''}}</td><td>${{r.service_name || ''}}</td><td>${{r.release_decision || ''}}</td><td>${{r.max_p95_latency_ms ?? 0}}</td><td>${{r.stable_rps ?? 0}}</td><td>${{r.max_error_rate_percent ?? 0}}</td><td>${{r.report_html_path ? `<a href=\"${{r.report_html_path}}\">report</a>` : ''}}</td></tr>`).join('');
    const svg = document.getElementById('chart');
    const w = 900, h = 320, pad = 44;
    svg.setAttribute('viewBox', `0 0 ${{w}} ${{h}}`);
    const maxP95 = Math.max(1, ...runs.map(r => Number(r.max_p95_latency_ms || 0)));
    const maxRps = Math.max(1, ...runs.map(r => Number(r.stable_rps || 0)));
    const x = i => pad + (runs.length <= 1 ? 0 : i * (w - pad * 2) / (runs.length - 1));
    const yP = v => h - pad - (Number(v || 0) / maxP95) * (h - pad * 2);
    const yR = v => h - pad - (Number(v || 0) / maxRps) * (h - pad * 2);
    const path = (fn, key) => runs.map((r,i) => `${{i ? 'L' : 'M'}} ${{x(i)}} ${{fn(r[key])}}`).join(' ');
    svg.innerHTML = `
      <text x=\"${{pad}}\" y=\"22\">x-axis: run time/order</text>
      <text x=\"${{pad}}\" y=\"42\">left y-axis: p95 latency ms, right y-axis: stable RPS</text>
      <line x1=\"${{pad}}\" y1=\"${{h-pad}}\" x2=\"${{w-pad}}\" y2=\"${{h-pad}}\" stroke=\"currentColor\" opacity=\"0.4\"/>
      <line x1=\"${{pad}}\" y1=\"${{pad}}\" x2=\"${{pad}}\" y2=\"${{h-pad}}\" stroke=\"currentColor\" opacity=\"0.4\"/>
      <path d=\"${{path(yP, 'max_p95_latency_ms')}}\" fill=\"none\" stroke=\"#b8322a\" stroke-width=\"3\"/>
      <path d=\"${{path(yR, 'stable_rps')}}\" fill=\"none\" stroke=\"#2f6f46\" stroke-width=\"3\"/>
      <text x=\"${{w-pad-160}}\" y=\"22\" fill=\"#b8322a\">p95 latency</text>
      <text x=\"${{w-pad-160}}\" y=\"42\" fill=\"#2f6f46\">stable RPS</text>`;
  </script>
</body>
</html>
""",
    )
    return output_path
