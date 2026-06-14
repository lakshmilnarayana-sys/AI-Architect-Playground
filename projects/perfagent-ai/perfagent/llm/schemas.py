from __future__ import annotations

from typing import TypedDict


class BottleneckExplanation(TypedDict):
    summary: str
    bottleneck: str
    confidence: str
    evidence: list[str]
    recommendations: list[str]
    missing_metrics: list[str]

