"""Push the golden dataset to LangSmith (Day 1 deliverable).

Prereqs:
    export LANGSMITH_API_KEY=...        # or LANGCHAIN_API_KEY
    # optional: export LANGSMITH_ENDPOINT=...

Usage:
    .venv/bin/python -m evaluation.incident.upload_dataset
    .venv/bin/python -m evaluation.incident.upload_dataset --recreate   # drop & re-create

The dataset name is versioned so baseline and post-improvement runs compare
against the exact same examples.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.incident.build_dataset import DATASET_VERSION

HERE = Path(__file__).resolve().parent
DATASET_FILE = HERE / "golden_dataset.json"
DATASET_NAME = "incident-response-golden"


def load_cases() -> list[dict]:
    if not DATASET_FILE.exists():
        raise SystemExit(
            f"{DATASET_FILE} not found. Run: python -m evaluation.incident.build_dataset"
        )
    return json.loads(DATASET_FILE.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=DATASET_NAME)
    ap.add_argument("--recreate", action="store_true",
                    help="delete an existing dataset of the same name first")
    args = ap.parse_args()

    from langsmith import Client

    client = Client()
    cases = load_cases()

    if client.has_dataset(dataset_name=args.name):
        if args.recreate:
            client.delete_dataset(dataset_name=args.name)
            print(f"Deleted existing dataset {args.name!r}")
        else:
            raise SystemExit(
                f"Dataset {args.name!r} already exists. Re-run with --recreate to replace it."
            )

    dataset = client.create_dataset(
        args.name,
        description=(
            "Week-4 golden dataset for the multi-agent incident-response pipeline "
            f"(Triage->Diagnose->Mitigate->Resolve->Postmortem). Version {DATASET_VERSION}. "
            "Mix: 50% happy / 30% edge / 15% known-failure / 5% adversarial."
        ),
        metadata={"dataset_version": DATASET_VERSION, "source": "evaluation/incident"},
    )

    examples = [
        {"inputs": c["inputs"], "outputs": c["outputs"], "metadata": c["metadata"]}
        for c in cases
    ]
    client.create_examples(dataset_id=dataset.id, examples=examples)

    print(f"Uploaded {len(examples)} examples to dataset {args.name!r} "
          f"(version {DATASET_VERSION}).")
    print(f"Dataset id: {dataset.id}")


if __name__ == "__main__":
    main()
