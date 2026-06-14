from __future__ import annotations


def classify_pr_complexity(changed_files: list[str]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    for path in changed_files:
        lowered = path.lower()
        if lowered.startswith(("migrations/", "db/", "database/")) or lowered.endswith(".sql"):
            score += 5
            reasons.append("database migration changed")
        if any(token in lowered for token in ["kafka", "redis", "cassandra", "elasticsearch", "postgres"]):
            score += 4
            reasons.append("dependency integration changed")
        if lowered.startswith(("services/", "src/", "app/")) and not lowered.endswith((".md", ".txt")):
            score += 3
            reasons.append("service code changed")
        if any(name in lowered for name in ["dockerfile", "docker-compose", "helm", "k8s", "deployment"]):
            score += 3
            reasons.append("runtime or infrastructure changed")
    unique_reasons = list(dict.fromkeys(reasons))
    if score >= 7:
        level = "high"
        profile = "full-regression"
    elif score >= 3:
        level = "medium"
        profile = "targeted"
    else:
        level = "low"
        profile = "smoke"
    return {"level": level, "score": score, "recommended_profile": profile, "reasons": unique_reasons}
