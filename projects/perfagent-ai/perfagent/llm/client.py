from __future__ import annotations

from typing import Any


def explain_bottleneck(structured_evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "LLM analysis is disabled in the MVP local path; deterministic evidence was used.",
        "input": structured_evidence,
    }

