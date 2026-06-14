from __future__ import annotations

from typing import Any


def build_traffic_replay_plan(contract: dict[str, Any], traffic_profile: dict[str, Any]) -> dict[str, Any]:
    endpoints = contract.get("endpoints", [])
    mix = traffic_profile.get("endpoint_mix", []) if traffic_profile.get("enabled") else []
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for item in mix:
        path = item.get("path", "")
        endpoint = _match_endpoint(path, endpoints)
        if endpoint:
            matched.append(
                {
                    "observed_path": path,
                    "contract_path": endpoint["path"],
                    "method": endpoint["method"],
                    "operation_id": endpoint.get("operation_id"),
                    "weight": item.get("weight", 0),
                    "observed_rps": item.get("observed_rps", 0),
                }
            )
        else:
            unmatched.append(item)
    total_weight = sum(float(item.get("weight", 0) or 0) for item in matched)
    if total_weight:
        for item in matched:
            item["normalized_weight"] = round(float(item["weight"]) / total_weight, 6)
    return {
        "enabled": bool(mix),
        "source": traffic_profile.get("source", "none"),
        "production_like_rps": traffic_profile.get("production_like_rps", 0),
        "peak_rps": traffic_profile.get("peak_rps", 0),
        "matched_endpoints": matched,
        "unmatched_endpoints": unmatched,
        "warnings": _warnings(matched, unmatched),
    }


def apply_replay_plan_to_strategy(strategy: dict[str, Any], replay_plan: dict[str, Any]) -> dict[str, Any]:
    if not replay_plan.get("matched_endpoints"):
        return strategy
    updated = dict(strategy)
    updated["endpoint_mix"] = [
        {
            "path": item["contract_path"],
            "operation_id": item.get("operation_id"),
            "weight": item.get("normalized_weight", item.get("weight", 0)),
            "observed_rps": item.get("observed_rps", 0),
        }
        for item in replay_plan["matched_endpoints"]
    ]
    updated["traffic_model"] = "observed-production-replay"
    return updated


def _match_endpoint(path: str, endpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    for endpoint in endpoints:
        if endpoint.get("path") == path:
            return endpoint
    path_parts = path.strip("/").split("/")
    for endpoint in endpoints:
        template_parts = str(endpoint.get("path", "")).strip("/").split("/")
        if len(template_parts) != len(path_parts):
            continue
        if all(template == observed or (template.startswith("{") and template.endswith("}")) for template, observed in zip(template_parts, path_parts)):
            return endpoint
    return None


def _warnings(matched: list[dict[str, Any]], unmatched: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if unmatched:
        warnings.append(f"{len(unmatched)} observed endpoints did not match the API contract")
    if not matched:
        warnings.append("no observed endpoints matched the API contract")
    return warnings
