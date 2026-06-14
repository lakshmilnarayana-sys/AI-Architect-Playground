BOTTLENECK_EXPLANATION_PROMPT = """You are a senior performance engineer.
Use only the provided structured evidence. Do not invent missing metrics.
Return strict JSON with summary, bottleneck, confidence, evidence, recommendations, and missing_metrics.
"""

REPORT_NARRATIVE_PROMPT = """Write a production-grade performance engineering report narrative.
Use only values provided in the structured input.
"""

