# PerfAgent MVP Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working CLI-first PerfAgent AI MVP slice from OpenAPI input to generated artifacts and reports.

**Architecture:** A Typer CLI calls a deterministic filesystem workflow. Core modules own parsing, generation, execution, analysis, and rendering so LangGraph and Prometheus can wrap the same functions later.

**Tech Stack:** Python 3.11+, Typer, PyYAML, Jinja2, pytest, optional local k6 executable.

---

### Task 1: Bootstrap And CLI Workspace

**Files:**
- Create: `pyproject.toml`
- Create: `perfagent/cli.py`
- Create: `perfagent/core/state.py`
- Create: `perfagent/core/workspace.py`
- Test: `tests/test_cli_workspace.py`

- [ ] Write a failing CLI test that invokes `perfagent evaluate` with `--skip-run` and asserts a run directory plus `state/evaluation_state.json` are created.
- [ ] Run `pytest tests/test_cli_workspace.py -v` and verify it fails because the package and command do not exist.
- [ ] Implement the Typer app, run ID generation, workspace directories, OpenAPI input copy, and serialized initial state.
- [ ] Run `pytest tests/test_cli_workspace.py -v` and verify it passes.

### Task 2: OpenAPI Parser

**Files:**
- Create: `perfagent/parsers/openapi_parser.py`
- Create: `examples/sample-openapi.yaml`
- Test: `tests/test_openapi_parser.py`

- [ ] Write a failing test that parses the sample spec and expects endpoints, methods, operation IDs, body schemas, required fields, and path/query parameters.
- [ ] Run `pytest tests/test_openapi_parser.py -v` and verify it fails because the parser does not exist.
- [ ] Implement YAML/JSON loading and endpoint extraction for OpenAPI `paths`.
- [ ] Run the parser test and verify it passes.

### Task 3: Synthetic Data Generator

**Files:**
- Create: `perfagent/generators/synthetic_data.py`
- Test: `tests/test_synthetic_data.py`

- [ ] Write a failing test that generates deterministic payloads from required string, number, boolean, object, and array schema fields.
- [ ] Run `pytest tests/test_synthetic_data.py -v` and verify it fails because generation does not exist.
- [ ] Implement deterministic schema walking with non-PII test values and seed-aware counters.
- [ ] Run the synthetic data test and verify it passes.

### Task 4: k6 Script Generator

**Files:**
- Create: `perfagent/generators/k6_generator.py`
- Test: `tests/test_k6_generator.py`

- [ ] Write a failing test that generates a JS file containing k6 imports, request methods, JSON bodies, checks, thresholds, and target URL interpolation.
- [ ] Run `pytest tests/test_k6_generator.py -v` and verify it fails because the generator does not exist.
- [ ] Implement a conservative single-file k6 generator.
- [ ] Run the k6 generator test and verify it passes.

### Task 5: Execution And Feature Analysis

**Files:**
- Create: `perfagent/collectors/k6_collector.py`
- Create: `perfagent/agents/execution_agent.py`
- Create: `perfagent/analyzers/features.py`
- Create: `perfagent/analyzers/bottlenecks.py`
- Test: `tests/test_feature_extraction.py`
- Test: `tests/test_bottleneck_rules.py`

- [ ] Write failing tests for summary parsing, SLO release decision, and deterministic bottleneck rules.
- [ ] Run the tests and verify they fail because the analyzer modules do not exist.
- [ ] Implement k6 subprocess execution with a missing-k6 warning path, summary parsing, feature extraction, release decision logic, and bottleneck classification.
- [ ] Run analyzer tests and verify they pass.

### Task 6: Reports And End-To-End Generate

**Files:**
- Create: `perfagent/generators/report_renderer.py`
- Create: `perfagent/templates/report.md.j2`
- Create: `perfagent/templates/report.html.j2`
- Create: `perfagent/workflow.py`
- Test: `tests/test_cli_workspace.py`

- [ ] Extend the CLI test to assert `generate` creates `contract_analysis.json`, `test_data.json`, `perf_test.js`, `report.md`, and `report.html`.
- [ ] Run the CLI test and verify it fails because the full workflow is not wired.
- [ ] Wire the CLI through parse, strategy, data, k6 generation, optional execution, feature extraction, bottleneck rules, and report rendering.
- [ ] Run all tests and verify they pass.
