from __future__ import annotations

import json
from typing import Any


def find_similar_regressions(
    *,
    query: str,
    runs: list[dict[str, Any]],
    vector_matches: list[dict[str, Any]] | None = None,
    service_name: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Combine deterministic run filtering with optional semantic retrieval."""
    sql_candidates = _filter_sql_candidates(runs, service_name=service_name, limit=limit)
    matches = vector_matches or []
    evidence = _build_evidence(sql_candidates, matches)
    summary = _summarize(query=query, candidates=sql_candidates, matches=matches)
    return {
        "query": query,
        "service_name": service_name,
        "summary": summary,
        "sql_candidates": sql_candidates,
        "vector_matches": matches[:limit],
        "evidence": evidence,
        "missing_metrics": _missing_metrics(sql_candidates),
    }


def _filter_sql_candidates(
    runs: list[dict[str, Any]],
    *,
    service_name: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for run in runs:
        if service_name and run.get("service_name") != service_name:
            continue
        features = _features_for_run(run)
        decision = str(run.get("release_decision", "")).upper()
        p95 = float(features.get("max_p95_latency_ms", run.get("max_p95_latency_ms", 0)) or 0)
        error_rate = float(features.get("max_error_rate_percent", run.get("max_error_rate_percent", 0)) or 0)
        breakpoint_rps = float(features.get("breaking_point_rps", features.get("estimated_capacity_rps", 0)) or 0)
        if decision in {"WARN", "BLOCK"} or p95 > 0 or error_rate > 0:
            candidates.append(
                {
                    "run_id": run.get("run_id"),
                    "service_name": run.get("service_name"),
                    "created_at": run.get("created_at"),
                    "release_decision": run.get("release_decision", "UNKNOWN"),
                    "max_p95_latency_ms": p95,
                    "max_error_rate_percent": error_rate,
                    "stable_rps": float(features.get("stable_rps", run.get("stable_rps", 0)) or 0),
                    "breaking_point_rps": breakpoint_rps,
                    "first_slo_breach_phase": features.get("first_slo_breach_phase"),
                    "report_html_path": run.get("report_html_path", ""),
                }
            )
    candidates.sort(
        key=lambda item: (
            item["release_decision"] == "BLOCK",
            item["release_decision"] == "WARN",
            item["max_p95_latency_ms"],
            item["max_error_rate_percent"],
        ),
        reverse=True,
    )
    return candidates[:limit]


def _features_for_run(run: dict[str, Any]) -> dict[str, Any]:
    raw = run.get("features_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def _build_evidence(candidates: list[dict[str, Any]], matches: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for candidate in candidates[:3]:
        evidence.append(
            f"{candidate['run_id']} was {candidate['release_decision']} with p95={candidate['max_p95_latency_ms']}ms "
            f"and error_rate={candidate['max_error_rate_percent']}%."
        )
    for match in matches[:3]:
        evidence.append(
            f"Vector match {match.get('run_id')} {match.get('chunk_type')}#{match.get('chunk_index')} "
            f"distance={match.get('distance')}."
        )
    return evidence


def _summarize(*, query: str, candidates: list[dict[str, Any]], matches: list[dict[str, Any]]) -> str:
    if not candidates and not matches:
        return "No similar regressions were found in structured history or vector context."
    parts = [f"Similar-regression search for: {query}."]
    if candidates:
        worst = candidates[0]
        parts.append(
            f"Structured history found {len(candidates)} candidate run(s); strongest match is {worst['run_id']} "
            f"with decision {worst['release_decision']} and p95 {worst['max_p95_latency_ms']} ms."
        )
    if matches:
        parts.append(f"Vector retrieval returned {len(matches)} narrative/log chunk(s) for AI explanation context.")
    return " ".join(parts)


def _missing_metrics(candidates: list[dict[str, Any]]) -> list[str]:
    missing = set()
    for candidate in candidates:
        if not candidate.get("breaking_point_rps"):
            missing.add("breaking_point_rps")
        if not candidate.get("first_slo_breach_phase"):
            missing.add("first_slo_breach_phase")
    return sorted(missing)
