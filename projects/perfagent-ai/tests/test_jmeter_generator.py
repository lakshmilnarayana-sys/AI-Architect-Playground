from pathlib import Path
from xml.etree import ElementTree

from perfagent.generators.jmeter_generator import generate_jmeter_plan


def test_generate_jmeter_plan_contains_thread_group_and_http_samplers(tmp_path):
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
    strategy = {"load": {"users": 25, "ramp_up_seconds": 10, "duration_seconds": 60}}

    output = tmp_path / "test_plan.jmx"
    generate_jmeter_plan(contract, test_data, strategy, "http://localhost:8080", output)

    root = ElementTree.parse(output).getroot()
    xml = ElementTree.tostring(root, encoding="unicode")
    assert 'testname="PerfAgent Test Plan"' in xml
    assert 'testname="PerfAgent Load Thread Group"' in xml
    assert 'testname="createPayment"' in xml
    assert '<stringProp name="HTTPSampler.method">POST</stringProp>' in xml
    assert 'testname="health"' in xml
    assert '<stringProp name="HTTPSampler.method">GET</stringProp>' in xml
