import json
from pathlib import Path
from generate_oncall_seed import build_seed

def test_build_seed_has_billing(tmp_path):
    # uses the real repo data/graph dirs
    root = Path(__file__).resolve().parents[2]
    seed = build_seed(root / "data", root / "graph")
    assert "oncall" in seed and "escalation" in seed
    # billing-service should resolve a team from OWNS_SERVICE (Billing Platform)
    assert "billing-service" in seed["oncall"]
    assert seed["oncall"]["billing-service"]["team"]
