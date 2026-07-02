"""Tests for the Week-4 incident-response evaluation harness."""
from evaluation.incident import evaluators as E
from evaluation.incident.build_dataset import build
from evaluation.incident.run_agent import run_incident_target


# --- dataset invariants ----------------------------------------------------- #
def test_dataset_size_and_mix():
    cases = build()
    assert len(cases) == 40
    counts = {}
    for c in cases:
        counts[c["metadata"]["scenario_type"]] = counts.get(c["metadata"]["scenario_type"], 0) + 1
    assert counts == {"happy": 20, "edge": 12, "known_failure": 6, "adversarial": 2}


def test_every_case_has_inputs_and_reference():
    for c in build():
        assert c["inputs"]["incident_id"]
        out = c["outputs"]
        assert "expected_team" in out
        assert "required_artifacts" in out
        assert isinstance(out["expected_mitigation_keyphrases"], list)


# --- code-based evaluators -------------------------------------------------- #
def test_failure_mode_accuracy_match_and_miss():
    ref = {"expected_failure_mode": "oom_kill"}
    assert E.failure_mode_accuracy({"active_failure": "oom_kill"}, ref, {})["score"] == 1.0
    assert E.failure_mode_accuracy({"active_failure": "cpu_throttle"}, ref, {})["score"] == 0.0


def test_mitigation_partial_credit():
    ref = {"expected_mitigation_keyphrases": ["memory limit", "1536mi", "canary"]}
    out = {"mitigation_plan": "Increase memory limit to 1536Mi and roll a node"}
    res = E.mitigation_correctness(out, ref, {})
    assert 0.6 < res["score"] < 0.7  # 2/3 phrases matched


def test_task_completion_zero_on_error():
    ref = {"required_artifacts": ["owner", "rca"]}
    assert E.task_completion({"error": "boom", "present_artifacts": []}, ref, {})["score"] == 0.0


def test_rediagnose_trajectory():
    rec = {"expects_rediagnose": False}
    notrec = {"expects_rediagnose": True}
    assert E.rediagnose_trajectory({"diagnose_attempts": 1}, rec, {})["score"] == 1.0
    assert E.rediagnose_trajectory({"diagnose_attempts": 1}, notrec, {})["score"] == 0.0
    assert E.rediagnose_trajectory({"diagnose_attempts": 2}, notrec, {})["score"] == 1.0


def test_oncall_paged_requires_person():
    ref = {"expected_oncall": "Emma Chen"}
    assert E.oncall_paged({"oncall_name": "Playback Primary On-call"}, ref, {})["score"] == 0.0
    assert E.oncall_paged({"oncall_name": "Paging Emma Chen now"}, ref, {})["score"] == 1.0


# --- end-to-end smoke ------------------------------------------------------- #
def test_happy_case_runs_and_scores_well():
    case = next(c for c in build() if c["id"] == "real-playback-oom-sev1")
    out = run_incident_target(case["inputs"])
    assert out["error"] is None
    assert E.failure_mode_accuracy(out, case["outputs"], case["inputs"])["score"] == 1.0
    assert E.owning_team_accuracy(out, case["outputs"], case["inputs"])["score"] == 1.0
    assert E.task_completion(out, case["outputs"], case["inputs"])["score"] == 1.0
