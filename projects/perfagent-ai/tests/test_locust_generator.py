from pathlib import Path

from perfagent.generators.locust_generator import generate_locustfile


def test_generate_locustfile_contains_http_user_tasks_and_payloads(tmp_path):
    contract = {
        "endpoints": [
            {"method": "POST", "path": "/v1/payments", "operation_id": "createPayment", "expected_status": 201},
            {"method": "GET", "path": "/health", "operation_id": "health", "expected_status": 200},
        ]
    }
    test_data = {
        "endpoints": [
            {
                "operation_id": "createPayment",
                "method": "POST",
                "path": "/v1/payments",
                "headers": {"x-request-id": "test-request"},
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
            },
        ]
    }

    output = tmp_path / "locustfile.py"
    generate_locustfile(contract, test_data, "http://localhost:8080", output)

    content = output.read_text()
    assert "from locust import HttpUser, between, task" in content
    assert "class PerfAgentUser(HttpUser):" in content
    assert 'host = "http://localhost:8080"' in content
    assert "def createPayment(self):" in content
    assert 'self.client.post("/v1/payments"' in content
    assert "def health(self):" in content
    assert 'self.client.get("/health"' in content
