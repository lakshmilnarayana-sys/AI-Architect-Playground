"""Hand-verified ground truth for the incident-response golden dataset.

Every map here was checked against the live source of truth on 2026-06-24:

- ``SERVICE_TO_TEAM`` / ``SERVICE_TO_ONCALL`` -- ``graph/edges.csv`` OWNS_SERVICE
  and CURRENT_PRIMARY_ONCALL edges.
- ``SERVICE_SEV_ESCALATION`` -- ``data/escalation_policies.yaml`` (only the four
  policies that actually exist; everything else is a deliberate coverage gap).
- ``MITIGATION_KEYPHRASES`` -- substrings lifted from the deterministic plan
  templates in ``src/incident/mitigate.py``.

Keeping the labels here (not inline in the dataset) means a single edit keeps the
whole golden set in sync if the agent's grounding data changes.
"""
from __future__ import annotations

import re

# Primary owning team per service base name (OWNS_SERVICE edges).
SERVICE_TO_TEAM = {
    "playback": "Platform Engineering",
    "manifest": "Platform Engineering",
    "cdn-routing": "Platform Engineering",
    "billing": "Billing Platform",
    "payment-gateway": "Billing Platform",
    "identity": "Security Governance",
    "audit-evidence": "Security Governance",
    "recommendation": "Recommendation Systems",
    "feature-store": "Recommendation Systems",
    "observability": "Reliability Engineering",
}

# Current primary on-call person per service base name.
SERVICE_TO_ONCALL = {
    "playback": "Emma Chen",
    "manifest": "Emma Chen",
    "cdn-routing": "Emma Chen",
    "billing": "Daniel Okafor",
    "payment-gateway": "Daniel Okafor",
    "identity": "Yuki Tanaka",
    "audit-evidence": "Yuki Tanaka",
    "recommendation": "Omar Hassan",
    "feature-store": "Omar Hassan",
    "observability": "Emma Chen",
}

# (service base, severity) -> expected escalation policy name.
# Only these four policies exist; any other pairing should resolve to None,
# which is itself a measurable coverage gap.
SERVICE_SEV_ESCALATION = {
    ("playback", "SEV1"): "Playback SEV1 Escalation Policy",
    ("billing", "SEV2"): "Billing SEV2 Escalation Policy",
    ("identity", "SEV1"): "Security SEV1 Escalation Policy",
    ("recommendation", "SEV2"): "Recommendation SEV2 Escalation Policy",
}

# Failure mode -> lowercased substrings that must appear in a correct mitigation
# plan. Pulled verbatim from src/incident/mitigate.py plan templates.
MITIGATION_KEYPHRASES = {
    "oom_kill": ["memory limit", "1536mi", "canary"],
    "pod_restart": ["exit code 137", "roll back"],
    "disk_iops": ["provisioned iops", "pvc latency"],
    "cpu_throttle": ["cpu limit", "hpa", "throttled ratio"],
    "memory_leak": ["heap profiles", "rss"],
    "node_pressure": ["cordon", "evict"],
    "image_pull_backoff": ["known-good image", "registry credentials"],
    "hpa_maxed": ["hpa max replicas", "queue depth"],
    "config_regression": ["revert", "config"],
    "dependency_timeout": ["circuit-breaker", "dependency"],
    "ingress_5xx": ["ingress", "5xx"],
    "network_packet_loss": ["packet loss", "retransmits"],
    "db_connection_pool_exhaustion": ["pool limits", "stuck sessions"],
    "kafka_consumer_lag": ["consumers", "lag"],
    "redis_hot_key": ["hot key", "redis"],
    "certificate_expiry": ["certificate", "handshakes"],
    "model_serving_errors": ["model variant", "inference error"],
    "feature_store_stale": ["fallback features", "feature freshness"],
    "log_pipeline_backpressure": ["collectors", "dropped log"],
    "metrics_cardinality_explosion": ["cardinality", "active series"],
}

# Artifacts every completed incident run must produce in `findings`.
REQUIRED_ARTIFACTS = [
    "owner",
    "rca",
    "mitigation_plan",
    "postmortem_md",
    "action_items",
]


def service_base(service: str) -> str:
    """Normalize a service name to its base token.

    "playback-service" / "Playback Service" -> "playback";
    "cdn-routing-service" -> "cdn-routing".
    """
    s = re.sub(r"\s+", "-", str(service or "").strip().lower())
    s = re.sub(r"-service$", "", s)
    return s


def expected_team(service: str) -> str | None:
    return SERVICE_TO_TEAM.get(service_base(service))


def expected_oncall(service: str) -> str | None:
    return SERVICE_TO_ONCALL.get(service_base(service))


def expected_escalation(service: str, severity: str) -> str | None:
    return SERVICE_SEV_ESCALATION.get((service_base(service), str(severity).upper()))


def expected_mitigation_keyphrases(failure_mode: str | None) -> list[str]:
    return MITIGATION_KEYPHRASES.get(failure_mode or "", [])
