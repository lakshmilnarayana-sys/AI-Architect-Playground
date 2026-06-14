from perfagent.analyzers.bottlenecks import classify_bottleneck


def test_classify_cpu_saturation_when_latency_and_cpu_are_high():
    features = {
        "max_p95_latency_ms": 920,
        "slo_p95_latency_ms": 500,
        "cpu_peak_percent": 91,
        "cpu_throttling_peak_percent": 0,
        "max_error_rate_percent": 0.2,
        "slo_error_rate_percent": 1,
        "memory_growth_rate_mb_per_min": 0,
        "memory_recovered": True,
    }

    analysis = classify_bottleneck(features)

    assert analysis["bottleneck"] == "cpu_saturation"
    assert analysis["confidence"] == "high"
    assert "CPU usage exceeded 85%" in analysis["evidence"]


def test_classify_dependency_unknown_when_latency_rises_without_saturation():
    features = {
        "max_p95_latency_ms": 920,
        "slo_p95_latency_ms": 500,
        "cpu_peak_percent": 62,
        "cpu_throttling_peak_percent": 0,
        "max_error_rate_percent": 0.2,
        "slo_error_rate_percent": 1,
        "memory_growth_rate_mb_per_min": 1,
        "memory_recovered": True,
    }

    analysis = classify_bottleneck(features)

    assert analysis["bottleneck"] == "dependency_or_unknown"
    assert analysis["confidence"] == "medium"
    assert "CPU and memory did not show saturation" in analysis["evidence"]
