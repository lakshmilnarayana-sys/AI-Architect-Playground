from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import parse, request


def collect_observability_traffic_profile(
    provider_config: dict[str, Any],
    service_name: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    provider = str(provider_config.get("provider", provider_config.get("source", ""))).lower()
    if provider == "datadog":
        return collect_datadog_traffic_profile(provider_config, service_name, start=start, end=end)
    if provider in {"newrelic", "new_relic"}:
        return collect_newrelic_traffic_profile(provider_config, service_name, start=start, end=end)
    if provider in {"elasticsearch", "elk"}:
        return collect_elasticsearch_traffic_profile(provider_config, service_name, start=start, end=end)
    return {"enabled": False, "source": provider or "unknown", "endpoint_mix": [], "warnings": ["unsupported observability provider"]}


def build_provider_query_pack(provider: str, service_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    provider_name = provider.lower()
    if provider_name == "datadog":
        queries = {
            "request_rate": "sum:trace.http.request.hits{service:{service}} by {resource_name}.as_rate()",
            "latency_p95": "p95:trace.http.request.duration{service:{service}} by {resource_name}",
            "error_rate": "sum:trace.http.request.errors{service:{service}} by {resource_name}.as_rate()",
        }
        required = ["api_key", "app_key", "site"]
    elif provider_name in {"newrelic", "new_relic"}:
        queries = {
            "request_rate": "SELECT rate(count(*), 1 second) FROM Transaction WHERE appName = '{service}' FACET request.uri",
            "latency_p95": "SELECT percentile(duration, 95) FROM Transaction WHERE appName = '{service}' FACET request.uri",
            "error_rate": "SELECT percentage(count(*), WHERE error IS true) FROM Transaction WHERE appName = '{service}' FACET request.uri",
        }
        required = ["account_id", "api_key"]
    elif provider_name in {"elasticsearch", "elk"}:
        queries = {
            "request_rate": {"terms_field": config.get("endpoint_field", "url.path"), "service_field": config.get("service_field", "service.name")},
            "latency_p95": {"percentile_field": config.get("duration_field", "event.duration"), "percentile": 95},
            "error_rate": {"error_field": config.get("error_field", "event.outcome")},
        }
        required = ["base_url", "index"]
    else:
        return {"provider": provider_name or "unknown", "supported": False, "queries": {}, "required_config": [], "warnings": ["unsupported provider"]}
    rendered = {
        name: _render_query(query, service_name)
        for name, query in queries.items()
    }
    return {
        "provider": provider_name,
        "supported": True,
        "service_name": service_name,
        "queries": rendered,
        "required_config": required,
        "warnings": [],
    }


def validate_provider_query_pack(provider: str, service_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    pack = build_provider_query_pack(provider, service_name, config)
    missing = [key for key in pack.get("required_config", []) if not config.get(key)]
    pack["valid"] = bool(pack.get("supported")) and not missing
    pack["missing_config"] = missing
    if missing:
        pack["warnings"] = [*pack.get("warnings", []), "missing provider config: " + ", ".join(missing)]
    return pack


def collect_datadog_traffic_profile(
    config: dict[str, Any],
    service_name: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    end = end or datetime.now(UTC)
    start = start or end - _lookback_delta(str(config.get("lookback", "6h")))
    query = str(config.get("request_rate_query", "sum:trace.http.request.hits{service:{service}} by {resource_name}.as_rate()"))
    query = query.replace("{service}", service_name)
    base_url = str(config.get("site", config.get("base_url", "https://api.datadoghq.com"))).rstrip("/")
    params = parse.urlencode({"from": int(start.timestamp()), "to": int(end.timestamp()), "query": query})
    headers = {"Accept": "application/json", "DD-API-KEY": str(config.get("api_key", "")), "DD-APPLICATION-KEY": str(config.get("app_key", ""))}
    payload = _json_request(base_url + "/api/v1/query?" + params, headers=headers)
    totals: dict[str, float] = {}
    endpoint_label = str(config.get("endpoint_label", "resource_name"))
    for series in payload.get("series", []):
        path = _extract_datadog_label(series, endpoint_label)
        if not path:
            continue
        points = series.get("pointlist", []) or []
        totals[path] = max(totals.get(path, 0.0), max((_safe_float(point[1]) for point in points), default=0.0))
    return _traffic_profile("datadog", config, totals, query=query)


def collect_newrelic_traffic_profile(
    config: dict[str, Any],
    service_name: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    end = end or datetime.now(UTC)
    start = start or end - _lookback_delta(str(config.get("lookback", "6h")))
    account_id = config.get("account_id")
    nrql = str(
        config.get(
            "nrql",
            "SELECT rate(count(*), 1 second) AS rps FROM Transaction WHERE appName = '{service}' FACET request.uri",
        )
    ).replace("{service}", service_name)
    if "SINCE" not in nrql.upper():
        nrql += f" SINCE '{_format_time(start)}' UNTIL '{_format_time(end)}'"
    graphql = {
        "query": "query($accountId: Int!, $nrql: Nrql!) { actor { account(id: $accountId) { nrql(query: $nrql) { results } } } }",
        "variables": {"accountId": int(account_id), "nrql": nrql},
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json", "Api-Key": str(config.get("api_key", ""))}
    payload = _json_request(str(config.get("base_url", "https://api.newrelic.com/graphql")), headers=headers, body=graphql)
    results = payload.get("data", {}).get("actor", {}).get("account", {}).get("nrql", {}).get("results", [])
    totals: dict[str, float] = {}
    endpoint_label = str(config.get("endpoint_label", "request.uri"))
    for row in results:
        path = row.get(endpoint_label) or row.get("facet") or row.get("name")
        if path:
            totals[str(path)] = max(totals.get(str(path), 0.0), _first_numeric(row, exclude={endpoint_label, "facet", "name"}))
    return _traffic_profile("newrelic", config, totals, query=nrql)


def collect_elasticsearch_traffic_profile(
    config: dict[str, Any],
    service_name: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    end = end or datetime.now(UTC)
    start = start or end - _lookback_delta(str(config.get("lookback", "6h")))
    endpoint_field = str(config.get("endpoint_field", "url.path"))
    service_field = str(config.get("service_field", "service.name"))
    count_field = str(config.get("count_field", "doc_count"))
    index = str(config.get("index", "logs-*"))
    body = config.get("query") or {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {service_field: service_name}},
                    {"range": {"@timestamp": {"gte": _format_time(start), "lte": _format_time(end)}}},
                ]
            }
        },
        "aggs": {"endpoints": {"terms": {"field": endpoint_field, "size": int(config.get("limit", 20))}}},
    }
    base_url = str(config.get("base_url", "http://localhost:9200")).rstrip("/")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if config.get("api_key"):
        headers["Authorization"] = "ApiKey " + str(config["api_key"])
    payload = _json_request(base_url + "/" + index + "/_search", headers=headers, body=body)
    totals = {
        str(bucket.get("key")): _safe_float(bucket.get(count_field, bucket.get("doc_count", 0)))
        for bucket in payload.get("aggregations", {}).get("endpoints", {}).get("buckets", [])
        if bucket.get("key")
    }
    elapsed_seconds = max((end - start).total_seconds(), 1)
    totals = {path: value / elapsed_seconds for path, value in totals.items()}
    return _traffic_profile("elasticsearch", config, totals, query=body)


def _traffic_profile(source: str, config: dict[str, Any], totals: dict[str, float], *, query: Any) -> dict[str, Any]:
    total_rps = sum(totals.values())
    peak_multiplier = float(config.get("peak_multiplier", 1.5))
    endpoint_mix = [
        {"path": path, "observed_rps": round(rps, 6), "weight": round((rps / total_rps) if total_rps else 0, 6)}
        for path, rps in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "enabled": True,
        "source": source,
        "observed_peak_rps": round(total_rps, 6),
        "production_like_rps": round(total_rps, 6),
        "peak_rps": round(total_rps * peak_multiplier, 6),
        "peak_multiplier": peak_multiplier,
        "endpoint_mix": endpoint_mix,
        "query": query,
    }


def _json_request(url: str, *, headers: dict[str, str], body: Any | None = None, timeout_seconds: int = 15) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers=headers)
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _render_query(query: Any, service_name: str) -> Any:
    if isinstance(query, str):
        return query.replace("{service}", service_name)
    if isinstance(query, dict):
        return {key: _render_query(value, service_name) for key, value in query.items()}
    return query


def _extract_datadog_label(series: dict[str, Any], label: str) -> str | None:
    for tag in series.get("tag_set", []) or series.get("scope", "").split(","):
        if ":" not in tag:
            continue
        key, value = tag.split(":", 1)
        if key == label:
            return value
    return series.get("metric")


def _first_numeric(row: dict[str, Any], *, exclude: set[str]) -> float:
    for key, value in row.items():
        if key in exclude:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _lookback_delta(value: str) -> timedelta:
    value = value.strip()
    if value.endswith("m"):
        return timedelta(minutes=float(value[:-1]))
    if value.endswith("h"):
        return timedelta(hours=float(value[:-1]))
    if value.endswith("d"):
        return timedelta(days=float(value[:-1]))
    return timedelta(seconds=float(value.rstrip("s")))


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
