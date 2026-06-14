from __future__ import annotations

import json
from typing import Any
from urllib import request

from perfagent.llm.prompts import BOTTLENECK_EXPLANATION_PROMPT


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


def explain_bottleneck(structured_evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": False,
        "summary": "LLM analysis is disabled. Deterministic evidence was used.",
        "input": structured_evidence,
    }


def explain_with_ollama(
    structured_evidence: dict[str, Any],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    prompt = _build_prompt(structured_evidence)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    endpoint = base_url.rstrip("/") + "/api/generate"
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        result = json.loads(response.read().decode("utf-8"))
    parsed = _parse_ollama_response(result.get("response", ""))
    parsed.update({"enabled": True, "provider": "ollama", "model": model})
    return parsed


def disabled_ai_analysis(reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "provider": "none",
        "summary": reason,
        "bottleneck": "not_run",
        "confidence": "none",
        "evidence": [],
        "recommendations": [],
        "missing_metrics": [],
    }


def _build_prompt(structured_evidence: dict[str, Any]) -> str:
    return (
        BOTTLENECK_EXPLANATION_PROMPT
        + "\n\nStructured evidence JSON:\n"
        + json.dumps(structured_evidence, indent=2, sort_keys=True)
    )


def _parse_ollama_response(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = {"summary": value.strip()}
    return {
        "summary": str(parsed.get("summary", "")),
        "bottleneck": str(parsed.get("bottleneck", "unknown")),
        "confidence": str(parsed.get("confidence", "unknown")),
        "evidence": list(parsed.get("evidence", [])),
        "recommendations": list(parsed.get("recommendations", [])),
        "missing_metrics": list(parsed.get("missing_metrics", [])),
    }
