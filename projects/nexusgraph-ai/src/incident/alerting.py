from __future__ import annotations


ALERT_THRESHOLDS = {
    "oom_kill": {"metric": "kube_pod_container_status_terminated_reason", "threshold": ">= 1 OOMKilled pod for 5m"},
    "pod_restart": {"metric": "kube_pod_container_status_restarts_total", "threshold": "restart delta >= 3 for 10m"},
    "disk_iops": {"metric": "volume_iops_utilization", "threshold": ">= 90% for 10m"},
    "cpu_throttle": {"metric": "container_cpu_cfs_throttled_ratio", "threshold": ">= 25% for 10m"},
}


def evaluate_alert(incident: dict) -> dict:
    """Simulate an observability alert evaluator for deterministic demos."""
    failure_mode = incident.get("failure_mode")
    threshold = ALERT_THRESHOLDS.get(str(failure_mode or ""))
    signal = incident.get("signal", "")
    severity = incident.get("severity", "SEV3")
    triggered = bool(threshold or severity in {"SEV1", "SEV2"})
    metric = threshold["metric"] if threshold else "service_slo_burn_rate"
    threshold_text = threshold["threshold"] if threshold else "customer-impacting SLO breach"
    return {
        "triggered": triggered,
        "source": "Grafana Alertmanager",
        "service": (incident.get("affected_services") or ["unknown"])[0],
        "metric": metric,
        "threshold": threshold_text,
        "reason": f"{metric} crossed threshold {threshold_text}; signal: {signal}",
        "severity": severity,
    }
