from __future__ import annotations


def format_stage_elapsed(stage: dict) -> str:
    elapsed = stage.get("elapsed")
    if elapsed is None:
        if stage.get("status") == "skipped":
            return "skipped"
        return "not timed"
    return f"{float(elapsed):.2f}s"


def evidence_counts(trace: dict | None) -> dict:
    evidence = (trace or {}).get("evidence", {})
    return {
        "vector": len(evidence.get("vector", [])),
        "graph": len(evidence.get("graph", [])),
        "merged": len(evidence.get("merged", [])),
    }
