from perfagent.config import default_strategy


def test_default_strategy_uses_short_warmup_and_recovery_for_ci_smoke_runs():
    strategy = default_strategy("10s", 500, 1)

    assert strategy["stages"] == [
        {"duration": "10s", "target": 10},
        {"duration": "10s", "target": 50},
        {"duration": "10s", "target": 100},
        {"duration": "10s", "target": 10},
    ]
