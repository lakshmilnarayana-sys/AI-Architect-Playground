"""Local eval harness — runs the agent over the golden dataset and scores it
with the code-based evaluators, no LangSmith account required.

This is the same logic LangSmith's client.evaluate runs on Day 2/3; running it
locally first validates the evaluators and gives an immediate baseline.

    .venv/bin/python -m evaluation.incident.run_local
    INCIDENT_USE_LLM=true .venv/bin/python -m evaluation.incident.run_local  # + judges

Writes evaluation/incident/baseline_local.json.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from evaluation.incident.build_dataset import build
from evaluation.incident.run_agent import run_incident_target, _flag
from evaluation.incident import evaluators as E

HERE = Path(__file__).resolve().parent
OUT = HERE / "baseline_local.json"


def _evaluator_fns():
    fns = list(E.CODE_EVALUATORS)
    if _flag("INCIDENT_USE_LLM"):
        from src.hybrid_rag import get_llm
        fns += E.make_llm_judges(get_llm())
    return fns


def main() -> None:
    cases = build()
    fns = _evaluator_fns()

    per_case = []
    scores_by_metric: dict[str, list[float]] = defaultdict(list)
    scores_by_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for c in cases:
        inputs = dict(c["inputs"])
        inputs["_scenario_type"] = c["metadata"]["scenario_type"]
        outputs = run_incident_target(c["inputs"])
        case_scores = {}
        for fn in fns:
            res = fn(outputs, c["outputs"], inputs)
            case_scores[res["key"]] = res["score"]
            scores_by_metric[res["key"]].append(res["score"])
            scores_by_type[c["metadata"]["scenario_type"]][res["key"]].append(res["score"])
        per_case.append({
            "id": c["id"],
            "type": c["metadata"]["scenario_type"],
            "error": outputs.get("error"),
            "scores": case_scores,
        })

    summary = {k: round(statistics.mean(v), 3) for k, v in scores_by_metric.items()}
    by_type = {
        t: {k: round(statistics.mean(v), 3) for k, v in metrics.items()}
        for t, metrics in scores_by_type.items()
    }

    report = {
        "dataset_size": len(cases),
        "use_llm": _flag("INCIDENT_USE_LLM"),
        "use_neo4j": _flag("INCIDENT_USE_NEO4J"),
        "use_vector": _flag("INCIDENT_USE_VECTOR"),
        "summary_by_metric": summary,
        "summary_by_scenario_type": by_type,
        "per_case": per_case,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"\nBaseline over {len(cases)} cases "
          f"(llm={_flag('INCIDENT_USE_LLM')}, neo4j={_flag('INCIDENT_USE_NEO4J')}):\n")
    width = max(len(k) for k in summary)
    for k in sorted(summary):
        bar = "#" * int(round(summary[k] * 20)) if summary[k] <= 1 else ""
        val = f"{summary[k]:.3f}"
        print(f"  {k:<{width}}  {val:>6}  {bar}")
    errored = [c["id"] for c in per_case if c["error"]]
    if errored:
        print(f"\n  errored cases ({len(errored)}): {', '.join(errored)}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
