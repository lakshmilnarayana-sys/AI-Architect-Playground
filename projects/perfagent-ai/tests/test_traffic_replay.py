from perfagent.collectors.traffic_replay import apply_replay_plan_to_strategy, build_traffic_replay_plan


def test_build_traffic_replay_plan_matches_template_paths():
    contract = {
        "endpoints": [
            {"method": "GET", "path": "/v1/payments/{id}", "operation_id": "getPayment"},
            {"method": "GET", "path": "/health", "operation_id": "health"},
        ]
    }
    profile = {
        "enabled": True,
        "source": "prometheus",
        "production_like_rps": 100,
        "peak_rps": 150,
        "endpoint_mix": [
            {"path": "/v1/payments/123", "weight": 0.8, "observed_rps": 80},
            {"path": "/unknown", "weight": 0.2, "observed_rps": 20},
        ],
    }

    plan = build_traffic_replay_plan(contract, profile)

    assert plan["matched_endpoints"][0]["operation_id"] == "getPayment"
    assert plan["matched_endpoints"][0]["normalized_weight"] == 1.0
    assert plan["unmatched_endpoints"][0]["path"] == "/unknown"


def test_apply_replay_plan_to_strategy_sets_weighted_mix():
    strategy = {"traffic_model": "observed-production", "endpoint_mix": []}
    plan = {
        "matched_endpoints": [
            {"contract_path": "/v1/payments", "operation_id": "createPayment", "normalized_weight": 1, "observed_rps": 100}
        ]
    }

    updated = apply_replay_plan_to_strategy(strategy, plan)

    assert updated["traffic_model"] == "observed-production-replay"
    assert updated["endpoint_mix"][0]["operation_id"] == "createPayment"
