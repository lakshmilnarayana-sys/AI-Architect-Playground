from pathlib import Path

from perfagent.generators.k6_generator import generate_k6_script


def test_generate_k6_script_contains_requests_thresholds_and_checks(tmp_path):
    contract = {
        "endpoints": [
            {
                "method": "POST",
                "path": "/v1/payments",
                "operation_id": "createPayment",
                "expected_status": 201,
            },
            {
                "method": "GET",
                "path": "/health",
                "operation_id": "health",
                "expected_status": 200,
            }
        ]
    }
    test_data = {
        "endpoints": [
            {
                "operation_id": "createPayment",
                "method": "POST",
                "path": "/v1/payments",
                "headers": {"x-request-id": "test-x-request-id-1001"},
                "body": {"amount": 49.99},
                "query": {},
                "path_params": {},
            },
            {
                "operation_id": "health",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "body": None,
                "query": {},
                "path_params": {},
            }
        ]
    }
    strategy = {
        "thresholds": {"p95_latency_ms": 500, "error_rate_percent": 1},
        "stages": [{"duration": "1m", "target": 10}],
    }

    output = tmp_path / "perf_test.js"
    generate_k6_script(contract, test_data, strategy, "http://localhost:8080", output)

    script = output.read_text()
    assert "import http from 'k6/http';" in script
    assert "http.post(`${BASE_URL}/v1/payments`" in script
    assert "http_req_duration: ['p(95)<500']" in script
    assert "http_req_failed: ['rate<0.01']" in script
    assert "summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)']" in script
    assert "check(res, { 'createPayment status is 201':" in script
    assert script.count("let res =") == 1
    assert "res = http.get(`${BASE_URL}/health`" in script
