from src.incident.kubernetes import (
    clear_failure,
    get_service_resource,
    inject_failure,
    load_kubernetes_resources,
)


def test_load_kubernetes_resources_uses_planned_data_contract():
    resources = load_kubernetes_resources()
    assert any(resource["service"] == "playback-service" for resource in resources)


def test_get_service_resource_returns_kv_context():
    resource = get_service_resource("playback-service")
    assert resource["namespace"] == "streamflix-prod"
    assert resource["kv"]["owner"] == "streaming-platform"


def test_inject_oom_failure_sets_runtime_symptoms_without_mutating_source():
    resource = get_service_resource("playback-service")
    runtime = inject_failure(resource, "oom_kill")
    assert runtime["active_failure"] == "oom_kill"
    assert runtime["pod_status"] == "OOMKilled"
    assert runtime["restart_count_delta"] == 4
    assert get_service_resource("playback-service")["failure_modes"]["oom_kill"]["enabled"] is False


def test_clear_failure_returns_healthy_runtime():
    resource = get_service_resource("playback-service")
    runtime = clear_failure(resource)
    assert runtime["active_failure"] is None
    assert runtime["pod_status"] == "Running"
    assert runtime["health"] == "healthy"
