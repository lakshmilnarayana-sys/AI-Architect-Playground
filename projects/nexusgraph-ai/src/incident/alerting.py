from __future__ import annotations


ALERT_THRESHOLDS = {
    "oom_kill": {"metric": "kube_pod_container_status_last_terminated_reason", "threshold": ">= 1 OOMKilled pod for 5m"},
    "pod_restart": {"metric": "kube_pod_container_status_restarts_total", "threshold": "restart delta >= 3 for 10m"},
    "disk_iops": {"metric": "volume_iops_utilization", "threshold": ">= 90% for 10m"},
    "cpu_throttle": {"metric": "container_cpu_cfs_throttled_ratio", "threshold": ">= 25% for 10m"},
    "memory_leak": {"metric": "container_memory_rss_growth_rate", "threshold": ">= 64Mi/min for 15m"},
    "node_pressure": {"metric": "kube_node_status_condition", "threshold": "MemoryPressure or DiskPressure true for 5m"},
    "image_pull_backoff": {"metric": "kube_pod_container_status_waiting_reason", "threshold": "ImagePullBackOff pods >= 2 for 5m"},
    "hpa_maxed": {"metric": "kube_horizontalpodautoscaler_status_desired_replicas", "threshold": "desired replicas >= max replicas for 10m"},
    "config_regression": {"metric": "deploy_config_change_error_ratio", "threshold": "error rate doubled within 15m of config rollout"},
    "dependency_timeout": {"metric": "upstream_request_timeout_rate", "threshold": "timeout rate >= 10% for 10m"},
    "ingress_5xx": {"metric": "nginx_ingress_controller_requests", "threshold": "5xx rate >= 5% for 5m"},
    "network_packet_loss": {"metric": "node_network_transmit_errs_total", "threshold": "packet loss >= 3% for 5m"},
    "db_connection_pool_exhaustion": {"metric": "db_pool_wait_queue_depth", "threshold": "pool utilization >= 95% and wait queue > 100 for 5m"},
    "kafka_consumer_lag": {"metric": "kafka_consumergroup_lag", "threshold": "consumer lag >= 100k messages for 10m"},
    "redis_hot_key": {"metric": "redis_command_duration_seconds", "threshold": "single key > 50k ops/sec and p99 >= 250ms"},
    "certificate_expiry": {"metric": "probe_ssl_earliest_cert_expiry", "threshold": "certificate expired or expires within 1h"},
    "model_serving_errors": {"metric": "model_inference_error_rate", "threshold": "inference error rate >= 5% for 10m"},
    "feature_store_stale": {"metric": "feature_freshness_lag_seconds", "threshold": "feature freshness lag >= 15m"},
    "log_pipeline_backpressure": {"metric": "fluentbit_output_retries_total", "threshold": "buffer utilization >= 90% for 10m"},
    "metrics_cardinality_explosion": {"metric": "prometheus_tsdb_head_series", "threshold": "active series growth >= 30% in 15m"},
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
