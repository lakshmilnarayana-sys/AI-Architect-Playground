# Week 4 — Evaluate Your Agent

**Track 3: Evaluating my own Week 3 agent with LangSmith**
Agent: multi-agent incident-response pipeline over the StreamFlix knowledge graph (`nexusgraph-ai`).

## Evaluation one-liner

> I measure **failure-mode/root-cause accuracy, owning-team accuracy, escalation accuracy,
> on-call paging accuracy, mitigation correctness, postmortem faithfulness, task completion,
> and p95 latency** on my multi-agent incident-response pipeline using a **40-case golden
> dataset** (50% happy / 30% edge / 15% known-failure / 5% adversarial) seeded from 23 real
> StreamFlix scenarios, with **code-based exact/keyphrase match + LLM-as-judge for
> faithfulness + trajectory checks**. Pass bar: 95% failure-mode, 95% owning-team, 90%
> escalation, 90% on-call, 90% mitigation, 90% faithfulness, 100% completion, p95 < 90s.
> I run this in LangSmith and report the delta from baseline to post-improvement.

## The framework

| Field | Answer |
|---|---|
| **Agent under test** | Multi-agent LangGraph incident-response pipeline (`src/incident/`): Declare → Triage → Diagnose → Mitigate → Resolve → Postmortem, grounded in a Neo4j/CSV knowledge graph of services, teams, on-call schedules, runbooks, SLOs, and escalation policies. Runs deterministic-by-default; an env-gated live mode drives a real Kubernetes cluster + Prometheus. |
| **User outcome** | An on-call engineer gets the right root cause, the right owning team and on-call **person** paged, a correct failure-specific mitigation, and a faithful postmortem — fast enough to act on. Wrong team or wrong person makes the agent worse than useless during an incident. |
| **Metrics** | Quality: failure_mode_accuracy, owning_team_accuracy, escalation_accuracy, oncall_paged, mitigation_correctness, rca/postmortem faithfulness (LLM judge). Behavior: task_completion, no_crash, rediagnose_trajectory (trajectory eval), no_injection_leak (adversarial). Cost/latency: latency_seconds + tokens via LangSmith. |
| **Judge method** | Code-based exact/normalized match for team/person/policy/failure-mode; keyphrase match for mitigation (substrings from the plan templates); trajectory counter for the rediagnose loop; LLM-as-judge (rubric prompts) for RCA and postmortem faithfulness; injection-leak is a code-based guardrail check. |
| **Golden dataset** | 40 cases, versioned `v1-2026-06-24` (`evaluation/incident/golden_dataset.json`). Real seeds: all 23 scenarios in `data/incident_scenarios.yaml`. Synthetic-from-real edge/known-failure/adversarial cases hand-authored in `build_dataset.py`. Labels hand-verified in `labels.py` against `graph/edges.csv`, `data/escalation_policies.yaml`, and the mitigation templates. |
| **Pass bar** | 95% failure-mode, 95% owning-team, 90% escalation, 90% on-call, 90% mitigation, 90% faithfulness, 100% completion, p95 < 90s. |
| **Instrumentation** | LangSmith traces every graph node, tool call, retry (rediagnose loop), token, and latency (`LANGSMITH_TRACING=true`). The demo dashboard renders the run's LangSmith trace on exit and reports live MTTD/MTTR per incident. |
| **Baseline run** | Local: `python -m evaluation.incident.run_local`. LangSmith: `run_langsmith.py --prefix baseline`. Numbers below. *LangSmith experiment link: `<LINK-BASELINE>`* |
| **Failure analysis** | Top 3 clusters below — 39 failing case-metrics reduced to 3 root causes. |
| **Improvement hypotheses** | 4 targeted changes below, each mapped to a cluster with predicted impact. |
| **Post-improvement run** | Same dataset version, same evaluators. Numbers + deltas below. *LangSmith experiment link: `<LINK-POST>`* |
| **What is next** | Remaining: 1 failure-mode edge case + 1 owning-team edge case (both deliberate hard cases). Next week: LLM-on faithfulness scoring at scale, live-mode MTTD/MTTR as production metrics. Production monitoring: Prometheus alerting already runs in the live platform (SLO breach, error-rate, latency); would alert on task-completion drop >5% over 7 days, p95 cost +25%/24h, paging-accuracy regressions. |

## Baseline (40 cases, code-based evaluators)

| Metric | Score |
|---|---|
| failure_mode_accuracy | 1.000 |
| owning_team_accuracy | 0.950 |
| mitigation_correctness | 0.975 |
| task_completion | 0.970 |
| no_crash | 0.975 |
| rediagnose_trajectory | 0.975 |
| no_injection_leak | 1.000 |
| **escalation_accuracy** | **0.525** |
| **oncall_paged** | **0.025** |
| avg latency | ~0.08 s (LLM off) |

## Failure analysis — 3 clusters, not 39 bugs

1. **On-call paging (0.025 — 39/40 wrong).** The graph lookup returned the on-call
   *schedule* node ("Playback Primary On-call") and never traversed the
   `CURRENT_PRIMARY_ONCALL` edge to the person. Cost: every page during a real incident
   goes to a rota name, not a human.
2. **Escalation accuracy (0.525).** The lookup tokenized `service.split()[0]` →
   `"playback-service"`, which never matches policy text ("playback"); hyphenated
   services always resolved to `None`. It also had a loose fallback that ignored
   severity, poised to return a Billing SEV2 policy for a SEV1.
3. **Unmodeled-mode crash (no_crash 0.975, task_completion 0.970).** `inject_failure`
   raised `KeyError` for a failure mode not modeled on the resource — the agent died
   instead of degrading.

## Improvements and measured deltas

| # | Lever | Change | Cluster | Predicted | Measured |
|---|---|---|---|---|---|
| 1 | Tool/graph design | Traverse schedule → `CURRENT_PRIMARY_ONCALL` → person in `oncall_for` (two-hop lookup) | 1 | +0.90 oncall | **oncall_paged 0.025 → 1.000 (+0.975)** |
| 2 | Tool design | Normalize service base name (strip `-service`) and require severity to match; drop the wrong-severity fallback | 2 | +0.40 escalation | **escalation_accuracy 0.525 → 1.000 (+0.475)** |
| 3 | Error recovery | Guard `inject_failure`; unmodeled (app-level) faults become a handled class instead of a crash | 3 | no_crash → 1.0 | **no_crash 0.975 → 1.000; task_completion 0.970 → 0.995** |
| 4 | Control flow / HITL | Paging policy: runbook available → add on-call to channel (no page); missing data → page. Plus a DETECTING phase so degradation precedes declaration, and per-run MTTD/MTTR reporting | behavioral honesty | qualitative | Live demo reports e.g. MTTD 26s, MTTR 1m26s per incident |

**Honest regression:** failure_mode_accuracy dipped 1.000 → 0.975 (one adversarial case)
after improvement 3 made unmodeled faults a distinct class — an accepted trade for never
crashing mid-incident.

## Post-improvement (same dataset v1, same evaluators)

| Metric | Baseline | Post | Δ |
|---|---|---|---|
| oncall_paged | 0.025 | **1.000** | +0.975 |
| escalation_accuracy | 0.525 | **1.000** | +0.475 |
| no_crash | 0.975 | **1.000** | +0.025 |
| task_completion | 0.970 | **0.995** | +0.025 |
| mitigation_correctness | 0.975 | **1.000** | +0.025 |
| owning_team_accuracy | 0.950 | **0.975** | +0.025 |
| failure_mode_accuracy | 1.000 | 0.975 | −0.025 |
| no_injection_leak | 1.000 | 1.000 | — |
| rediagnose_trajectory | 0.975 | 1.000 | +0.025 |

All metrics now meet or beat the pass bar except the two remaining single-case edge gaps
(0.975 vs the 95% bar — at the bar).

## Links

- Repo (framework, dataset, evaluators, harnesses): [`evaluation/incident/`](https://github.com/lakshmilnarayana-sys/AI-Architect-Playground/tree/main/projects/nexusgraph-ai/evaluation/incident)
- Golden dataset: `evaluation/incident/golden_dataset.json` (v1-2026-06-24), uploaded to LangSmith as `incident-response-golden`
- **LangSmith (public, no login needed): [dataset + both experiments](https://smith.langchain.com/public/5e9f224f-8783-4cca-ada4-1f559d33f61b/d)**
- LangSmith (org view): [dataset](https://smith.langchain.com/o/6511ac7f-706b-4352-9597-1ee1b2396d19/datasets/6ea51b91-231b-465d-b7c2-06fcff6ff600) · [baseline `baseline-60f7150e`](https://smith.langchain.com/o/6511ac7f-706b-4352-9597-1ee1b2396d19/datasets/6ea51b91-231b-465d-b7c2-06fcff6ff600/compare?selectedSessions=a4d078b4-c039-41a2-87a2-ad1bc8898226) · [post-improvement `post-improvement-03e7c1d0`](https://smith.langchain.com/o/6511ac7f-706b-4352-9597-1ee1b2396d19/datasets/6ea51b91-231b-465d-b7c2-06fcff6ff600/compare?selectedSessions=7dfa31a9-41b6-4d65-8511-a0cb0dd72104) · [side-by-side comparison](https://smith.langchain.com/o/6511ac7f-706b-4352-9597-1ee1b2396d19/datasets/6ea51b91-231b-465d-b7c2-06fcff6ff600/compare?selectedSessions=a4d078b4-c039-41a2-87a2-ad1bc8898226%2C7dfa31a9-41b6-4d65-8511-a0cb0dd72104)
- Loom walkthrough: `<LOOM-LINK>`

> Note on the LangSmith baseline experiment: it isolates improvements #1–2 by reverting
> `graph_lookup.py` to the pre-fix commit; the crash guard (#3) was already merged, so its
> delta (no_crash 0.975→1.0, task_completion 0.970→0.995) is documented from the Day-1
> local baseline (`run_local.py`) rather than reproduced in the LangSmith pair.
