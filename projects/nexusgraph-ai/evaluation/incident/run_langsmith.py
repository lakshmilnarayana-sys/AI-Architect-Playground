"""Run the eval suite against the golden dataset in LangSmith (Day 2/3).

Prereqs:
    export LANGSMITH_API_KEY=...                 # or LANGCHAIN_API_KEY
    export LANGSMITH_TRACING=true                # trace every agent run
    # optional, to use a real LLM for RCA/mitigation + enable the judges:
    export INCIDENT_USE_LLM=true OPENAI_API_KEY=...

Usage:
    .venv/bin/python -m evaluation.incident.run_langsmith --prefix baseline
    .venv/bin/python -m evaluation.incident.run_langsmith --prefix post-improvement

The run, per-metric scores, and full traces land under the LangSmith project so
baseline vs post-improvement can be diffed in the Comparison view.
"""
from __future__ import annotations

import argparse

from evaluation.incident.run_agent import run_incident_target, _flag, _maybe_llm
from evaluation.incident.evaluators import langsmith_evaluators
from evaluation.incident.upload_dataset import DATASET_NAME
from evaluation.incident.build_dataset import DATASET_VERSION


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET_NAME)
    ap.add_argument("--prefix", default="baseline",
                    help="experiment name prefix, e.g. baseline / post-improvement")
    args = ap.parse_args()

    from langsmith import evaluate

    judge_llm = _maybe_llm()  # None unless INCIDENT_USE_LLM is set
    evaluators = langsmith_evaluators(llm=judge_llm)

    def target(inputs: dict) -> dict:
        return run_incident_target(inputs)

    results = evaluate(
        target,
        data=args.dataset,
        evaluators=evaluators,
        experiment_prefix=args.prefix,
        metadata={
            "dataset_version": DATASET_VERSION,
            "use_llm": _flag("INCIDENT_USE_LLM"),
            "use_neo4j": _flag("INCIDENT_USE_NEO4J"),
            "use_vector": _flag("INCIDENT_USE_VECTOR"),
            "judges_enabled": judge_llm is not None,
        },
    )
    print(results)


if __name__ == "__main__":
    main()
