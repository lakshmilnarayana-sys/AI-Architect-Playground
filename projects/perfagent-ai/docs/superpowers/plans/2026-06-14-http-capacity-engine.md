# HTTP Capacity Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HTTP capacity and breakpoint detection evidence-backed using k6 JSONL time-series output and phase-aware bucket analysis.

**Architecture:** k6 execution exports both summary JSON and JSONL metric samples. A parser converts JSONL samples into 10-second buckets, maps buckets to configured phases, and feature extraction estimates capacity and first breakpoint from bucketed RPS, p95/p99, error rate, and VUs.

**Tech Stack:** Python stdlib, k6 JSON output, existing Typer CLI, pytest.

---

### Task 1: k6 JSONL Collection

**Files:**
- Modify: `perfagent/collectors/k6_collector.py`
- Modify: `perfagent/workflow.py`
- Test: `tests/test_k6_collector.py`

- [ ] Add a failing test that expects `run_k6` command construction to include `--out json=<raw/k6_timeseries.jsonl>` while preserving `--summary-export`.
- [ ] Update native and Docker command builders to accept a time-series path.
- [ ] Persist `raw_k6_timeseries_path` in execution result.
- [ ] Run collector tests.

### Task 2: k6 JSONL Parser And Alignment

**Files:**
- Modify: `perfagent/analyzers/alignment.py`
- Test: `tests/test_alignment.py`

- [ ] Add failing tests with sample k6 JSONL `Point` records for `http_reqs`, `http_req_duration`, `http_req_failed`, and `vus`.
- [ ] Implement parsing into 10-second buckets.
- [ ] Calculate per-bucket RPS, p95, p99, error rate percent, and virtual users.
- [ ] Map each bucket to warmup, baseline, stress, or recovery from strategy stage durations.
- [ ] Run alignment tests.

### Task 3: Capacity Features

**Files:**
- Modify: `perfagent/analyzers/features.py`
- Test: `tests/test_feature_extraction.py`

- [ ] Add tests for first SLO breach from bucketed rows.
- [ ] Calculate estimated capacity as highest RPS before breach.
- [ ] Calculate breaking point RPS, headroom, limit phase, and confidence.
- [ ] Ensure no-breach runs report tested peak as sustained capacity with correct caveat.
- [ ] Run feature tests.

### Task 4: Reports And CI Gate

**Files:**
- Modify: `perfagent/generators/report_renderer.py`
- Modify: `perfagent/cli.py`
- Test: `tests/test_cli_workspace.py`
- Test: `tests/test_report_renderer.py`

- [ ] Add report assertions for capacity and breakpoint fields.
- [ ] Add `--fail-on` option that exits non-zero for selected release decisions.
- [ ] Include capacity fields in `summary.json`.
- [ ] Run CLI and report tests.

### Task 5: Verification

**Files:**
- No new files expected.

- [ ] Run full test suite.
- [ ] Run `make inspect`.
- [ ] Run a skip-run CLI smoke check.
- [ ] Clean transient caches and generated outputs.
