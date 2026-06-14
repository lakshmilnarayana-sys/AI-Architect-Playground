from perfagent.generators.synthetic_data import generate_test_data


def test_generate_test_data_respects_required_fields_and_seed():
    contract = {
        "endpoints": [
            {
                "method": "POST",
                "path": "/v1/payments",
                "operation_id": "createPayment",
                "path_parameters": [],
                "query_parameters": [],
                "required_headers": ["x-request-id"],
                "request_schema": {
                    "type": "object",
                    "required": ["customerId", "amount", "currency", "metadata", "items"],
                    "properties": {
                        "customerId": {"type": "string"},
                        "amount": {"type": "number"},
                        "currency": {"type": "string", "enum": ["GBP", "USD"]},
                        "metadata": {
                            "type": "object",
                            "required": ["attempt"],
                            "properties": {"attempt": {"type": "integer"}},
                        },
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["sku"],
                                "properties": {"sku": {"type": "string"}},
                            },
                        },
                    },
                },
            }
        ]
    }

    generated = generate_test_data(contract, seed=1001)
    endpoint_data = generated["endpoints"][0]

    assert endpoint_data["headers"]["x-request-id"] == "test-x-request-id-1001"
    assert endpoint_data["body"] == {
        "customerId": "test_customerId_1001",
        "amount": 49.99,
        "currency": "GBP",
        "metadata": {"attempt": 1001},
        "items": [{"sku": "test_sku_1001"}],
    }
