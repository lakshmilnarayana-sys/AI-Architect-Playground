# Incident-Response Agent — Week 4 Evaluation

Evaluation of the multi-agent incident-response pipeline
(`Triage → Diagnose → Mitigate → Resolve → Postmortem`) in `src/incident/`.

## Evaluation one-liner

> I measure **failure-mode/root-cause accuracy, owning-team accuracy, escalation
> accuracy, on-call paging accuracy, mitigation correctness, postmortem
> faithfulness, task completion, and p95 latency** on the multi-agent
> incident-response pipeline using a **40-case golden dataset** (50% happy / 30%
> edge / 15% known-failure / 5% adversarial) seeded from 23 real StreamFlix
> scenarios, with **code-based exact/keyphrase match + LLM-as-judge for
> faithfulness + trajectory checks**. Pass bar: 95% failure-mode, 95% owning-team,
> 90% escalation, 90% on-call, 90% mitigation, 90% faithfulness, 100% completion,
> p95 < 90s. I run this in LangSmith and report the delta from baseline to
> post-improvement.

## The framework

| Field | Detail |
|---|---|
| **Agent under test** | Multi-agent LangGraph incident-response pipeline (`src/incident/`), run via `run_incident()`. |
| **User outcome** | An on-call engineer gets the right root cause, the right owning team/person paged, a correct failure-specific mitigation, and a faithful postmortem — fast enough to act on. |
| **Metrics** | Quality: failure_mode_accuracy, owning_team_accuracy, escalation_accuracy, oncall_paged, mitigation_correctness, rca/postmortem faithfulness. Behavior: task_completion, no_crash, rediagnose_trajectory, no_injection_leak. Cost/latency: latency_seconds (+ tokens via LangSmith). |
| **Judge method** | Code-based for everything machine-checkable (exact match, keyphrase, counters); LLM-as-judge for RCA & postmortem faithfulness. |
| **Golden dataset** | 40 cases. Real seeds from `data/incident_scenarios.yaml` (23); synthetic edge/known-failure/adversarial hand-authored in `build_dataset.py`. Labels in `labels.py`, verified against `graph/edges.csv`, `data/escalation_policies.yaml`, and the `mitigate.py` templates. |
| **Pass bar** | See one-liner. |
| **Instrumentation** | LangSmith traces every node, tool call, retry (rediagnose loop), token, and latency. `LANGSMITH_TRACING=true`. |
| **Baseline run** | Local baseline below (`run_local.py`); LangSmith baseline via `run_langsmith.py --prefix baseline` (Day 2/3). |
| **Failure analysis** | Day 3 — top clusters already visible: on-call person never resolved, escalation brittle on hyphenated names, unmodeled-mode crash. |
| **Improvement hypotheses** | Day 4 — see below. |
| **Post-improvement run** | Day 4 — `run_langsmith.py --prefix post-improvement`, diff in Comparison view. |

## Files

| File | Purpose |
|---|---|
| `labels.py` | Hand-verified ground-truth maps (service→team/on-call, escalation, mitigation keyphrases). |
| `build_dataset.py` | Assembles the 40-case dataset → `golden_dataset.json`. |
| `golden_dataset.json` | The versioned dataset artifact (`v1-2026-06-24`). |
| `run_agent.py` | Runs the pipeline for one input row → flat scorable output (never raises). |
| `evaluators.py` | Pure evaluator functions + LLM judges + LangSmith adapter. |
| `run_local.py` | Local harness: run + score the whole dataset, no LangSmith account needed. |
| `upload_dataset.py` | Push `golden_dataset.json` to LangSmith. |
| `run_langsmith.py` | Run `client.evaluate` against the LangSmith dataset. |
| `baseline_local.json` | Latest local baseline output. |

## Commands

```bash
# (re)build the dataset
.venv/bin/python -m evaluation.incident.build_dataset

# local baseline (code-based evaluators only)
.venv/bin/python -m evaluation.incident.run_local
# with real LLM + faithfulness judges
INCIDENT_USE_LLM=true OPENAI_API_KEY=... .venv/bin/python -m evaluation.incident.run_local

# LangSmith (Day 2/3)
export LANGSMITH_API_KEY=... LANGSMITH_TRACING=true
.venv/bin/python -m evaluation.incident.upload_dataset
.venv/bin/python -m evaluation.incident.run_langsmith --prefix baseline
```

## Baseline (local, code-based, llm=off, neo4j=off)

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
| latency_seconds (avg) | ~0.08s (no LLM) |

### Dominant failure clusters (Day 4 targets)

1. **On-call paging (0.025)** — `oncall_for` returns the on-call *schedule*
   ("Playback Primary On-call"), never traversing `CURRENT_PRIMARY_ONCALL` to the
   person. Fix: extend the graph lookup to resolve the person.
2. **Escalation accuracy (0.525)** — `escalation_for` tokenizes
   `service.split()[0]` = `"playback-service"`, which doesn't match policy text
   ("playback"). Hyphenated service names resolve to `None`. Fix: normalize the
   service name (strip `-service`) before matching.
3. **Robustness crash** — `inject_failure` raises `KeyError` for a failure mode
   not modeled on the resource (and on the fallback service). Fix: guard the
   injection and degrade gracefully.

## Post-improvement (local, code-based, llm=off, neo4j=off)

All three clusters fixed and measured over the same v1 dataset:

| Metric | Baseline | Post | Δ | Improvement |
|---|---|---|---|---|
| oncall_paged | 0.025 | **1.000** | **+0.975** | Traverse schedule → `CURRENT_PRIMARY_ONCALL` → person in `oncall_for` (graph lookup, second hop). |
| escalation_accuracy | 0.525 | **1.000** | **+0.475** | Normalize service base name (strip `-service`) and require the severity to match — a Billing SEV2 policy is no longer returned for a billing SEV1 incident. |
| no_crash | 0.975 | **1.000** | +0.025 | Guard `inject_failure` on unmodeled failure modes; agent degrades gracefully instead of raising. |
| task_completion | 0.970 | **0.995** | +0.025 | Follows from the crash guard (the errored case now completes). |
| failure_mode_accuracy | 1.000 | 0.975 | −0.025 | One adversarial/edge case regressed as app-level (unmodeled) faults became a distinct class — honest trade for no_crash 1.0. |
| owning_team_accuracy | 0.950 | 0.975 | +0.025 | — |
| mitigation_correctness | 0.975 | 1.000 | +0.025 | — |
| everything else | 1.000 | 1.000 | — | no_injection_leak, rediagnose_trajectory hold. |

Remaining gaps: one failure-mode case and one owning-team case (both deliberate
hard cases). Next: LLM-on faithfulness judges in LangSmith, and live-mode MTTD/MTTR
(now reported by the demo dashboard per run) as production metrics.

> Note: the local baseline runs with `INCIDENT_USE_LLM=off`, so RCA/mitigation
> use deterministic fallbacks and the faithfulness judges are skipped. The
> LangSmith baseline should be run with the LLM on to score faithfulness and
> capture real token/latency cost.
