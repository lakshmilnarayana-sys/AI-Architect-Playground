# Week 5 — Fine-Tune a Support Ticket Router (custom project)

**StreamFlix Incident Ticket Router** — instead of the stock IT-helpdesk dataset, this
fine-tunes Qwen/Qwen3-1.7B-Base (LoRA via LLaMA Factory / LLaMA Board, Colab T4) to route
StreamFlix incident tickets to one of **7 owning-team queues**, with ground truth derived
from the same knowledge graph that powers the rest of `nexusgraph-ai`
(`service → OWNED_BY_EXTERNAL_TEAM → team` edges — single source of truth).

All assets: [`finetuning/`](https://github.com/lakshmilnarayana-sys/AI-Architect-Playground/tree/main/projects/nexusgraph-ai/finetuning)

| Asset | What it is |
|---|---|
| `generate_tickets.py` | Deterministic dataset generator (seeded, byte-identical reruns). Symptom phrasing seeded from the 23 real incident scenarios, service logs, and modeled failure modes; 4 channel styles (email / Slack / portal / paraphrased alert). Verified: 840 rows, exactly 120 per queue, **zero label leakage**, zero duplicates. |
| `streamflix_tickets.csv` | The dataset (`category_truth,text`, mirroring the stock notebook schema). |
| `streamflix_ticket_router.ipynb` | Colab notebook mirroring the stock Week 5 phases 1–6: install → dataset prep (stratified 80/20, ShareGPT, `dataset_info.json`) → LLaMA Board LoRA training → loss-curve review → merge + `classify()` smoke test → validation classification report / confusion matrix + untuned-base letter-choice baseline vs fine-tuned delta. |
| `finetuning/README.md` | Business case, 7-queue table, dataset provenance, run steps, phase mapping. |

## Results (fill in after the Colab run)

- Loss curve screenshot: `<SCREENSHOT>`
- Validation accuracy — baseline (untuned, letter-choice): `<N%>` · fine-tuned: `<N%>` · delta: `<+N%>`
- Classification report + confusion matrix screenshot: `<SCREENSHOT>`
- Notable per-class wins/regressions: `<NOTES>`
