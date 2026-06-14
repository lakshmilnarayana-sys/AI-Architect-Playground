from __future__ import annotations

from statistics import mean
from typing import Any


LOAD_METRICS = {"rps", "virtual_users"}
LATENCY_METRICS = {"p95_latency_ms", "p99_latency_ms", "service_p95_latency", "service_p99_latency"}
ERROR_METRICS = {"error_rate_percent", "service_error_rate_percent", "5xx_error_rate"}
INFRA_METRICS = {"cpu_percent", "memory_mb", "cpu_throttling_percent", "pod_restarts"}


def analyze_timeseries(
    rows: list[dict[str, Any]],
    *,
    slo_p95_ms: float,
    slo_error_rate_percent: float,
) -> dict[str, Any]:
    numeric_metrics = _numeric_metrics(rows)
    solo = {metric: _solo_metric(metric, rows) for metric in numeric_metrics}
    breaches = _breach_windows(rows, slo_p95_ms=slo_p95_ms, slo_error_rate_percent=slo_error_rate_percent)
    correlations = _correlations(rows, numeric_metrics)
    phases = _phase_summaries(rows, numeric_metrics)
    recovery = _recovery(rows, slo_p95_ms=slo_p95_ms, slo_error_rate_percent=slo_error_rate_percent)
    return {
        "row_count": len(rows),
        "metrics_available": numeric_metrics,
        "missing_core_metrics": _missing_core_metrics(numeric_metrics),
        "solo_metrics": solo,
        "phase_summaries": phases,
        "slo_breaches": breaches,
        "correlations": correlations,
        "recovery": recovery,
    }


def reason_over_timeseries(
    *,
    timeseries_analysis: dict[str, Any],
    features: dict[str, Any],
    dependency_analysis: dict[str, Any] | None = None,
    profiling_artifacts: dict[str, Any] | None = None,
    profile_phase_correlation: dict[str, Any] | None = None,
    max_steps: int = 8,
) -> dict[str, Any]:
    tools = _tool_results(
        timeseries_analysis,
        features,
        dependency_analysis or {},
        profiling_artifacts or {},
        profile_phase_correlation or {},
    )
    ordered_tools = [
        "inspect_slo_breaches",
        "inspect_load_latency_correlation",
        "inspect_infra_correlation",
        "inspect_dependency_correlation",
        "inspect_profile_evidence",
        "inspect_profile_phase_alignment",
        "inspect_recovery",
        "inspect_missing_metrics",
    ][:max_steps]
    trace: list[dict[str, Any]] = []
    observations: list[str] = []
    for index, tool_name in enumerate(ordered_tools, start=1):
        observation = tools[tool_name]
        trace.append(
            {
                "step": index,
                "thought": _thought_for_tool(tool_name),
                "action": tool_name,
                "observation": observation,
            }
        )
        observations.extend(observation.get("evidence", []))

    conclusion = _conclude(
        timeseries_analysis,
        features,
        dependency_analysis or {},
        profiling_artifacts or {},
        profile_phase_correlation or {},
    )
    conclusion["evidence"] = _dedupe(observations + conclusion.get("evidence", []))
    return {
        "mode": "bounded_react",
        "max_steps": max_steps,
        "trace": trace,
        "conclusion": conclusion,
    }


def _numeric_metrics(rows: list[dict[str, Any]]) -> list[str]:
    metrics = set()
    for row in rows:
        for key, value in row.items():
            if key in {"timestamp", "phase"}:
                continue
            if _to_float(value) is not None:
                metrics.add(key)
    return sorted(metrics)


def _solo_metric(metric: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_to_float(row.get(metric)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"available": False}
    start = values[0]
    end = values[-1]
    peak = max(values)
    trough = min(values)
    slope = round(end - start, 6)
    return {
        "available": True,
        "start": start,
        "end": end,
        "min": trough,
        "max": peak,
        "avg": round(mean(values), 6),
        "slope": slope,
        "trend": _trend(slope, peak, trough),
    }


def _breach_windows(
    rows: list[dict[str, Any]],
    *,
    slo_p95_ms: float,
    slo_error_rate_percent: float,
) -> list[dict[str, Any]]:
    breaches = []
    for index, row in enumerate(rows):
        p95 = _to_float(row.get("p95_latency_ms")) or 0
        error_rate = _to_float(row.get("error_rate_percent")) or 0
        reasons = []
        if p95 > slo_p95_ms:
            reasons.append("p95_latency")
        if error_rate > slo_error_rate_percent:
            reasons.append("error_rate")
        if reasons:
            breaches.append(
                {
                    "index": index,
                    "timestamp": row.get("timestamp"),
                    "phase": row.get("phase"),
                    "rps": _to_float(row.get("rps")) or 0,
                    "p95_latency_ms": p95,
                    "error_rate_percent": error_rate,
                    "reasons": reasons,
                }
            )
    return breaches


def _correlations(rows: list[dict[str, Any]], metrics: list[str]) -> list[dict[str, Any]]:
    targets = [metric for metric in ["p95_latency_ms", "error_rate_percent"] if metric in metrics]
    inputs = [metric for metric in metrics if metric not in targets]
    results = []
    for target in targets:
        for metric in inputs:
            corr = _pearson(
                [_to_float(row.get(metric)) for row in rows],
                [_to_float(row.get(target)) for row in rows],
            )
            if corr is None:
                continue
            if abs(corr) >= 0.55:
                results.append(
                    {
                        "metric": metric,
                        "target": target,
                        "correlation": round(corr, 4),
                        "strength": "strong" if abs(corr) >= 0.75 else "moderate",
                    }
                )
    results.sort(key=lambda item: abs(item["correlation"]), reverse=True)
    return results


def _phase_summaries(rows: list[dict[str, Any]], metrics: list[str]) -> list[dict[str, Any]]:
    phases = []
    for phase in _ordered_phases(rows):
        phase_rows = [row for row in rows if row.get("phase") == phase]
        summary = {"phase": phase, "row_count": len(phase_rows)}
        for metric in metrics:
            values = [_to_float(row.get(metric)) for row in phase_rows]
            values = [value for value in values if value is not None]
            if values:
                summary[f"{metric}_avg"] = round(mean(values), 6)
                summary[f"{metric}_max"] = max(values)
        phases.append(summary)
    return phases


def _recovery(
    rows: list[dict[str, Any]],
    *,
    slo_p95_ms: float,
    slo_error_rate_percent: float,
) -> dict[str, Any]:
    if not rows:
        return {"status": "unknown", "evidence": ["no time-series rows available"]}
    recovery_rows = [row for row in rows if str(row.get("phase", "")).lower() == "recovery"]
    if not recovery_rows:
        recovery_rows = rows[-max(1, min(3, len(rows))) :]
    last = recovery_rows[-1]
    p95 = _to_float(last.get("p95_latency_ms")) or 0
    error_rate = _to_float(last.get("error_rate_percent")) or 0
    recovered = p95 <= slo_p95_ms and error_rate <= slo_error_rate_percent
    return {
        "status": "recovered" if recovered else "not_recovered",
        "last_timestamp": last.get("timestamp"),
        "last_phase": last.get("phase"),
        "last_p95_latency_ms": p95,
        "last_error_rate_percent": error_rate,
        "evidence": [
            f"final observed p95={p95}ms against SLO={slo_p95_ms}ms",
            f"final observed error_rate={error_rate}% against SLO={slo_error_rate_percent}%",
        ],
    }


def _tool_results(
    analysis: dict[str, Any],
    features: dict[str, Any],
    dependency_analysis: dict[str, Any],
    profiling_artifacts: dict[str, Any],
    profile_phase_correlation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    correlations = analysis.get("correlations", [])
    dependency_correlations = [
        item
        for item in correlations
        if str(item.get("metric", "")).startswith("dep_")
    ]
    infra_correlations = [
        item
        for item in correlations
        if item.get("metric") in INFRA_METRICS
    ]
    load_correlations = [
        item
        for item in correlations
        if item.get("metric") in LOAD_METRICS
    ]
    profile_functions = _profile_top_functions(profiling_artifacts)
    return {
        "inspect_slo_breaches": {
            "evidence": _breach_evidence(analysis.get("slo_breaches", []), features),
            "breach_count": len(analysis.get("slo_breaches", [])),
        },
        "inspect_load_latency_correlation": {
            "evidence": _correlation_evidence(load_correlations, "load"),
            "correlations": load_correlations,
        },
        "inspect_infra_correlation": {
            "evidence": _correlation_evidence(infra_correlations, "infra"),
            "correlations": infra_correlations,
        },
        "inspect_dependency_correlation": {
            "evidence": _correlation_evidence(dependency_correlations, "dependency")
            + _dependency_findings_evidence(dependency_analysis.get("findings", [])),
            "correlations": dependency_correlations,
            "findings": dependency_analysis.get("findings", []),
        },
        "inspect_profile_evidence": {
            "evidence": _profile_evidence(profile_functions),
            "top_functions": profile_functions[:10],
        },
        "inspect_profile_phase_alignment": {
            "evidence": _profile_phase_evidence(profile_phase_correlation),
            "capture_windows": profile_phase_correlation.get("capture_windows", []),
            "artifact_correlations": profile_phase_correlation.get("artifact_correlations", []),
        },
        "inspect_recovery": analysis.get("recovery", {"evidence": ["recovery status unavailable"]}),
        "inspect_missing_metrics": {
            "evidence": [
                f"missing core metric: {metric}" for metric in analysis.get("missing_core_metrics", [])
            ]
            or ["core load, latency, and error metrics are present"],
            "missing_core_metrics": analysis.get("missing_core_metrics", []),
        },
    }


def _conclude(
    analysis: dict[str, Any],
    features: dict[str, Any],
    dependency_analysis: dict[str, Any],
    profiling_artifacts: dict[str, Any],
    profile_phase_correlation: dict[str, Any],
) -> dict[str, Any]:
    correlations = analysis.get("correlations", [])
    dependency_findings = dependency_analysis.get("findings", [])
    profile_functions = _profile_top_functions(profiling_artifacts)
    profile_dependency_matches = _profile_dependency_matches(profile_functions, dependency_analysis)
    phase_dependency_matches = _profile_phase_dependency_matches(profile_phase_correlation, dependency_analysis)
    solo_metrics = analysis.get("solo_metrics", {})
    infra_hot = any(
        item.get("metric") in {"cpu_percent", "cpu_throttling_percent", "memory_mb"}
        and item.get("target") == "p95_latency_ms"
        for item in correlations
    ) and (
        float(solo_metrics.get("cpu_percent", {}).get("max", 0) or 0) >= 85
        or float(solo_metrics.get("cpu_throttling_percent", {}).get("max", 0) or 0) >= 5
        or solo_metrics.get("memory_mb", {}).get("trend") == "rising"
    )
    dependency_hot = any(str(item.get("metric", "")).startswith("dep_") for item in correlations) or bool(dependency_findings)
    load_hot = any(item.get("metric") == "rps" and item.get("target") == "p95_latency_ms" for item in correlations)
    breach_count = len(analysis.get("slo_breaches", []))
    if not analysis.get("row_count"):
        return {
            "classification": "insufficient_timeseries",
            "confidence": "low",
            "summary": "No aligned time-series rows were available, so autonomous reasoning cannot establish a breakpoint.",
            "evidence": [],
        }
    if dependency_hot and phase_dependency_matches:
        classification = "dependency_profile_phase_correlated_bottleneck"
        confidence = "high"
        summary = "Dependency metrics and profiling evidence overlap the failing phase, so the dependency-related hot path is tied to the observed SLO breach."
    elif dependency_hot and profile_dependency_matches:
        classification = "dependency_profile_correlated_bottleneck"
        confidence = "high"
        summary = "Dependency metrics and profiling evidence both point at dependency-related execution paths during the performance failure."
    elif dependency_hot:
        classification = "dependency_correlated_bottleneck"
        confidence = "high" if dependency_findings else "medium"
        summary = "Latency or errors correlate with dependency metrics, so the likely constraint is downstream or upstream dependency behavior."
    elif infra_hot:
        classification = "infrastructure_correlated_bottleneck"
        confidence = "medium"
        summary = "Latency correlates with infrastructure metrics, so CPU, memory, or throttling should be inspected first."
    elif load_hot and breach_count:
        classification = "load_induced_breakpoint"
        confidence = "medium"
        summary = "Latency rises with load and SLO breaches occur, indicating a measurable load-induced breakpoint."
    elif breach_count:
        classification = "slo_breach_without_clear_correlate"
        confidence = "low"
        summary = "SLO breaches are present, but current metrics do not identify a strong correlated bottleneck."
    else:
        classification = "no_bottleneck_detected"
        confidence = "medium"
        summary = "Observed time-series stayed within SLO and no strong bottleneck correlate was detected."
    return {
        "classification": classification,
        "confidence": confidence,
        "summary": summary,
        "estimated_capacity_rps": features.get("estimated_capacity_rps"),
        "breaking_point_rps": features.get("breaking_point_rps"),
        "first_slo_breach_phase": features.get("first_slo_breach_phase"),
        "evidence": _profile_phase_match_evidence(phase_dependency_matches) or _profile_match_evidence(profile_dependency_matches),
    }


def _breach_evidence(breaches: list[dict[str, Any]], features: dict[str, Any]) -> list[str]:
    if not breaches:
        return ["no SLO breach windows detected"]
    first = breaches[0]
    return [
        f"first breach at {first.get('timestamp')} phase={first.get('phase')} rps={first.get('rps')}",
        f"breach metrics p95={first.get('p95_latency_ms')}ms error_rate={first.get('error_rate_percent')}%",
        f"feature breakpoint_rps={features.get('breaking_point_rps')}",
    ]


def _correlation_evidence(correlations: list[dict[str, Any]], group: str) -> list[str]:
    if not correlations:
        return [f"no strong {group} correlation found"]
    return [
        f"{item['metric']} correlated with {item['target']} at {item['correlation']} ({item['strength']})"
        for item in correlations[:3]
    ]


def _dependency_findings_evidence(findings: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item.get('dependency')} {item.get('metric')} reached {item.get('value')} against threshold {item.get('threshold')}"
        for item in findings[:3]
    ]


def _profile_top_functions(profiling_artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = [
        *profiling_artifacts.get("profiles", []),
        *profiling_artifacts.get("auto_capture", {}).get("artifacts", []),
    ]
    functions: list[dict[str, Any]] = []
    for profile in profiles:
        summary = profile.get("summary", {})
        for item in summary.get("top_functions", []):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            functions.append(
                {
                    "name": name,
                    "percent": item.get("percent"),
                    "samples": item.get("samples"),
                    "profile_type": profile.get("type", "unknown"),
                    "artifact_path": profile.get("artifact_path"),
                }
            )
    functions.sort(key=lambda item: _to_float(item.get("percent")) or 0, reverse=True)
    return functions


def _profile_evidence(functions: list[dict[str, Any]]) -> list[str]:
    if not functions:
        return ["no profiling top-function evidence available"]
    return [
        f"profile hot function {item.get('name')} consumed {item.get('percent')}% samples={item.get('samples')}"
        for item in functions[:5]
    ]


def _profile_dependency_matches(
    functions: list[dict[str, Any]],
    dependency_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    dependency_terms = []
    for dependency in dependency_analysis.get("dependencies", []):
        for key in ("name", "type"):
            value = str(dependency.get(key) or "").lower()
            if value:
                dependency_terms.append(value)
    for finding in dependency_analysis.get("findings", []):
        value = str(finding.get("dependency") or "").lower()
        if value:
            dependency_terms.append(value)
    dependency_terms = sorted(set(dependency_terms), key=len, reverse=True)
    matches = []
    for function in functions:
        name = function["name"].lower()
        matched = next((term for term in dependency_terms if term and term in name), None)
        if matched:
            matches.append(function | {"matched_dependency": matched})
    return matches


def _profile_match_evidence(matches: list[dict[str, Any]]) -> list[str]:
    return [
        f"profile hot function {item.get('name')} matched dependency {item.get('matched_dependency')} at {item.get('percent')}%"
        for item in matches[:3]
    ]


def _profile_phase_evidence(profile_phase_correlation: dict[str, Any]) -> list[str]:
    artifacts = profile_phase_correlation.get("artifact_correlations", [])
    if not artifacts:
        return ["no profile phase correlation evidence available"]
    evidence = []
    for artifact in artifacts[:5]:
        phases = ", ".join(artifact.get("overlapped_phases", [])) or "none"
        breach = "overlaps first SLO breach" if artifact.get("breach_overlap") else "does not overlap first SLO breach"
        top = artifact.get("top_functions", [{}])[0].get("name") if artifact.get("top_functions") else "no top function"
        evidence.append(
            f"profile artifact {artifact.get('artifact_path')} overlaps phases={phases}; {breach}; top_function={top}"
        )
    return evidence


def _profile_phase_dependency_matches(
    profile_phase_correlation: dict[str, Any],
    dependency_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    dependency_terms = _dependency_terms(dependency_analysis)
    matches = []
    for artifact in profile_phase_correlation.get("artifact_correlations", []):
        if not artifact.get("breach_overlap"):
            continue
        for function in artifact.get("top_functions", []):
            name = str(function.get("name") or "").lower()
            matched = next((term for term in dependency_terms if term and term in name), None)
            if matched:
                matches.append(
                    function
                    | {
                        "matched_dependency": matched,
                        "artifact_path": artifact.get("artifact_path"),
                        "overlapped_phases": artifact.get("overlapped_phases", []),
                        "breach_overlap": artifact.get("breach_overlap"),
                    }
                )
    return matches


def _profile_phase_match_evidence(matches: list[dict[str, Any]]) -> list[str]:
    return [
        f"profile hot function {item.get('name')} matched dependency {item.get('matched_dependency')} during first SLO breach; phases={', '.join(item.get('overlapped_phases', []))}; percent={item.get('percent')}%"
        for item in matches[:3]
    ]


def _dependency_terms(dependency_analysis: dict[str, Any]) -> list[str]:
    dependency_terms = []
    for dependency in dependency_analysis.get("dependencies", []):
        for key in ("name", "type"):
            value = str(dependency.get(key) or "").lower()
            if value:
                dependency_terms.append(value)
    for finding in dependency_analysis.get("findings", []):
        value = str(finding.get("dependency") or "").lower()
        if value:
            dependency_terms.append(value)
    return sorted(set(dependency_terms), key=len, reverse=True)


def _missing_core_metrics(metrics: list[str]) -> list[str]:
    required = ["rps", "p95_latency_ms", "error_rate_percent"]
    return [metric for metric in required if metric not in metrics]


def _ordered_phases(rows: list[dict[str, Any]]) -> list[str]:
    phases = []
    for row in rows:
        phase = str(row.get("phase", "unknown"))
        if phase not in phases:
            phases.append(phase)
    return phases


def _pearson(left_raw: list[float | None], right_raw: list[float | None]) -> float | None:
    pairs = [(left, right) for left, right in zip(left_raw, right_raw, strict=False) if left is not None and right is not None]
    if len(pairs) < 3:
        return None
    left_values = [pair[0] for pair in pairs]
    right_values = [pair[1] for pair in pairs]
    left_mean = mean(left_values)
    right_mean = mean(right_values)
    numerator = sum((left - left_mean) * (right - right_mean) for left, right in pairs)
    left_denominator = sum((left - left_mean) ** 2 for left in left_values)
    right_denominator = sum((right - right_mean) ** 2 for right in right_values)
    denominator = (left_denominator * right_denominator) ** 0.5
    if not denominator:
        return None
    return numerator / denominator


def _trend(slope: float, peak: float, trough: float) -> str:
    spread = max(1.0, abs(peak - trough))
    if abs(slope) / spread < 0.1:
        return "flat"
    return "rising" if slope > 0 else "falling"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _thought_for_tool(tool_name: str) -> str:
    thoughts = {
        "inspect_slo_breaches": "Find the first objective failure window before reasoning about root cause.",
        "inspect_load_latency_correlation": "Check whether latency or errors rise as offered load rises.",
        "inspect_infra_correlation": "Check whether service resources move with the user-facing symptom.",
        "inspect_dependency_correlation": "Check whether declared dependencies explain the symptom better than local saturation.",
        "inspect_profile_evidence": "Check whether profiling hot functions corroborate the metric-based hypothesis.",
        "inspect_profile_phase_alignment": "Check whether profile capture overlaps the failing phase or first SLO breach window before making phase-specific profile claims.",
        "inspect_recovery": "Check whether the service returns to SLO after load drops.",
        "inspect_missing_metrics": "Identify which missing signals limit confidence.",
    }
    return thoughts.get(tool_name, "Inspect available evidence.")


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
