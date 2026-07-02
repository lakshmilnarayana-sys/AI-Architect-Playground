# Week 5 — Fine-Tune a StreamFlix Support Ticket Router

Gen Academy Week 5 custom project: a **LoRA fine-tune of `Qwen/Qwen3-1.7B-Base`**
(LLaMA Factory / LLaMA Board on a Colab T4) that routes StreamFlix incident tickets
to the correct **owning-team queue**.

## Business case

StreamFlix currently sends every inbound ticket — customer emails, Slack pings,
help-portal forms, paraphrased monitoring alerts — to a frontier model for
classification. That is slow (per-ticket API latency), expensive at ticket volume,
and ships internal incident text to a third party. A 1.7B model fine-tuned on our
own routing taxonomy runs on a single small GPU, answers in milliseconds, and its
labels are *our* queues, not a generic taxonomy. Chance on this balanced 7-class
task is ~14%; the notebook measures exactly how much the fine-tune beats the
untuned base model on the same tickets.

## The 7 queues

Labels are the 7 platform teams that own services via `OWNED_BY_EXTERNAL_TEAM`
edges in the knowledge graph:

| Queue (label) | Owns (examples) | Example downstream action |
|---|---|---|
| Content Discovery | catalog, metadata, search, recommendation, personalization | roll back ranker canary, rebuild search index |
| Core Platform | api-gateway, edge-router, config, experiments, observability | revert config rollout, drop high-cardinality metric label |
| Data Platform | event-ingestion, analytics, feature-store, ml-ranking | restart feature sync job, drain ingest backlog |
| Identity Platform | auth, profile, account, device-auth | rotate mTLS cert, relax MFA enforcement mode |
| Monetization Platform | billing, payment, invoice, subscription | refund duplicate captures, scale DB connection pool |
| Streaming Platform | playback, manifest, cdn-routing, license, subtitle | bump playback memory limits, fix CDN POP weights |
| User Engagement | notification, email, push, watchlist, ratings | flush dedupe cache, re-register push tokens |

## Dataset: generated from the knowledge graph

`generate_tickets.py` treats the graph as the **single source of truth**:

- **Labels**: `graph/edges.csv` → `service —OWNED_BY_EXTERNAL_TEAM→ team`; each ticket
  concerns one service and is labeled with its owning team's queue name.
- **Phrasing seeds**: incident signals from `data/incident_scenarios.yaml`, log lines
  from `data/service_logs.yaml`, and failure modes/triggers from
  `data/kubernetes_resources.yaml` (OOMKilled, CrashLoopBackOff, Kafka lag, cert
  expiry, cardinality explosion, ...), rendered in 4 channel styles (user email,
  Slack, help-portal form, human-paraphrased monitoring alert) with varied tone
  and verbosity.
- **No leakage**: an assertion guarantees no ticket text contains any queue label
  (case-insensitive) — the model must learn *service/symptom → team*, not string match.
- **Deterministic**: `random.Random(42)`; rerunning produces a byte-identical CSV.
- **Shape**: 840 rows, exactly 120 per queue, 0 duplicate texts.
  Schema mirrors the stock Week 5 `support_tickets.csv`: `category_truth,text`.

Regenerate with:

```bash
.venv/bin/python finetuning/generate_tickets.py
```

## How to run (Colab)

1. Generate `streamflix_tickets.csv` locally (command above) — or use the committed copy.
2. Open `streamflix_ticket_router.ipynb` in Google Colab; set runtime to **T4 GPU**.
3. Run Phase 1 (GPU check, clone + install LLaMA-Factory, ~5 min).
4. Run Phase 2; upload `streamflix_tickets.csv` when prompted. It splits 80/20
   (stratified), writes ShareGPT JSON, and registers dataset `streamflix_tickets`.
5. Run Phase 3 to launch **LLaMA Board**; in the UI pick model `Qwen/Qwen3-1.7B-Base`,
   template `qwen`, finetuning type `LoRA`, dataset `streamflix_tickets`, then Start
   (~15–25 min). Watch the loss curve; interrupt the cell when training finishes.
6. Run Phases 4–6: loss-curve review, adapter merge + 5-ticket smoke test, validation
   `classification_report` + confusion matrix, and the baseline-vs-fine-tuned
   accuracy delta (untuned base model, constrained A–G letter-choice prompt).

## Handout phase mapping

| Handout phase | This project |
|---|---|
| Phase 1 — Environment | GPU check (T4), clone LLaMA-Factory, `pip install -e .[torch,bitsandbytes]` |
| Phase 2 — Dataset | `streamflix_tickets.csv` → stratified 80/20 split → ShareGPT JSON → `dataset_info.json` entry `streamflix_tickets` |
| Phase 3 — Train | LLaMA Board webui: Qwen/Qwen3-1.7B-Base + LoRA on `streamflix_tickets` |
| Phase 4 — Loss curve | Markdown guide + optional re-plot from `trainer_log.jsonl` |
| Phase 5 — Merge & smoke test | `ADAPTER_DIR` → `merge_and_unload()` → `classify()` → 5-ticket smoke test |
| Phase 6 — Evaluate | sklearn report + confusion matrix; baseline = untuned base with letter-choice prompt; accuracy delta |

## Results

<!-- Paste screenshots after running the notebook -->

**Loss curve**

> _placeholder — screenshot of the LLaMA Board / Phase 4 loss curve_

**Validation metrics (classification report + confusion matrix)**

> _placeholder — screenshot of Phase 6a/6b output_

**Baseline vs fine-tuned**

> _placeholder — screenshot of Phase 6c/6d chart and accuracy delta_

## Files

- `generate_tickets.py` — deterministic dataset generator (graph → tickets)
- `streamflix_tickets.csv` — 840 labeled tickets (`category_truth,text`)
- `streamflix_ticket_router.ipynb` — Colab notebook (Phases 1–6)
