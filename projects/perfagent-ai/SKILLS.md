# PerfAgent AI Skills Context

This file is the model-agnostic operating guide for AI coding agents working on PerfAgent AI. It is intended for Codex, Claude, Gemini, Cursor, Goose, or any other agent that needs enough project context to make correct engineering decisions without rediscovering the product.

Detailed reusable skill material lives in:

```text
skills/performance-engineer/
```

Use that directory as the canonical performance-engineering skill pack. The root `SKILLS.md` gives the high-level context; the skill pack contains task-specific references.

## Product Context

PerfAgent AI is a CLI-first performance evaluation framework for microservices.

Core product promise:

```text
From API contract to performance report using deterministic evidence plus AI explanation.
```

Core question the product answers:

```text
Can this service handle expected load, where does it break, why does it break, and what should engineering fix first?
```

Primary users:

- Platform Engineering
- SRE
- Performance Engineering
- QA Engineering
- DevOps
- Service owners and release managers

## Engineering Principle

This is the most important rule:

```text
Code calculates the evidence.
LLM explains the evidence.
```

Do not let an LLM calculate or invent:

- p95 or p99 latency
- RPS
- error rate
- capacity
- breakpoints
- release decision
- dependency behavior
- CPU or memory saturation
- regression status

The deterministic code path must calculate those first. AI is only for narrative, recommendations, confidence explanation, and missing-metric explanation.

## Current Architecture

Main flow:

```text
OpenAPI spec
  -> contract analysis
  -> synthetic data generation
  -> load test generation
  -> test execution or external result import
  -> metrics collection
  -> time-series alignment
  -> feature extraction
  -> bottleneck/dependency classification
  -> AI explanation when enabled
  -> Markdown/interactive HTML report
  -> run persistence and regression comparison
```

Current execution engines:

- `k6`: first-class HTTP execution path.
- `locust`: generated file plus external result import.
- `jmeter`: generated plan plus external result import.
- `grpc`: generated Python gRPC harness and direct execution path.
- `websocket`: generated Python WebSocket harness and direct execution path.

Current observability integrations:

- Prometheus-compatible query API.
- Datadog traffic-profile adapter.
- New Relic traffic-profile adapter.
- Elasticsearch traffic-profile adapter.
- Configurable Prometheus dependency metrics.

Current storage:

- SQLite run store by default.
- Optional Postgres run store for shared CI.
- Configurable retention, default 30 days.
- Database/object storage is the source of truth for execution facts.
- Vector embeddings are only for semantic retrieval over narratives, findings, logs, recommendations, warnings, and profiling summaries.
- Do not use embeddings for p95/p99 comparison, regression gates, capacity calculation, trend analysis, release decisions, or baseline comparison.

Current AI integration:

- Ollama local model support.
- Default model examples use `llama3.2`.
- AI analysis is optional and must degrade gracefully.

## Repository Map

Important files and directories:

```text
perfagent/cli.py                         CLI commands
perfagent/config.py                      YAML and CLI option resolution
perfagent/workflow.py                    Evaluation orchestration
perfagent/parsers/openapi_parser.py      OpenAPI parsing
perfagent/generators/                    Test/report generators
perfagent/collectors/                    k6, protocol, Prometheus, provider collectors
perfagent/analyzers/                     Feature, SLO, bottleneck, dependency logic
perfagent/storage/                       SQLite and Postgres run stores
perfagent/llm/                           Ollama client and prompts
perfagent/templates/                     Markdown and HTML report templates
examples/                                Sample apps, configs, CI examples
docs/                                    Product and integration docs
tests/                                   Pytest coverage
skills/performance-engineer/             Detailed AI-agent skill pack
```

Generated run artifacts:

```text
input/openapi.yaml
generated/perf_test.js
generated/locustfile.py
generated/jmeter_test_plan.jmx
generated/grpc_load.py
generated/websocket_load.py
generated/test_data.json
raw/k6_summary.json
raw/k6_timeseries.jsonl
raw/prometheus_metrics.json
raw/dependency_metrics.json
raw/execution_result.json
processed/contract_analysis.json
processed/test_strategy.yaml
processed/metric_contract.yaml
processed/aligned_timeseries.csv
processed/features.json
processed/bottleneck_analysis.json
processed/dependency_analysis.json
processed/traffic_profile.json
processed/ai_analysis.json
reports/report.md
reports/report.html
reports/summary.json
state/evaluation_state.json
```

## Skill Pack Routing

When working on performance-engineering tasks, use:

```text
skills/performance-engineer/SKILL.md
```

Then load only the needed reference:

- `references/test-design.md`: workload design, SLOs, payloads, acceptance criteria.
- `references/protocols-and-tools.md`: k6, Locust, JMeter, gRPC, WebSocket, UI testing.
- `references/observability-and-dependencies.md`: Prometheus, Datadog, New Relic, Elasticsearch, DB/Kafka/Redis/Cassandra/search dependencies.
- `references/capacity-regression-ci.md`: capacity, breakpoints, baselines, regression, CI, retention.
- `references/reporting-ai-governance.md`: interactive reports, AI/Ollama, MCP, bottleneck rules, governance.
- `references/perfagent-project-map.md`: commands, file map, artifact paths, implementation conventions.

## Agent Instructions

For any AI agent:

1. Read local code before proposing changes.
2. Prefer existing patterns over new abstractions.
3. Keep deterministic analysis separate from LLM explanation.
4. Add tests for every new parser, generator, collector, analyzer, command, or storage path.
5. Keep docs and examples aligned with CLI behavior.
6. Verify with `make test` before claiming success.
7. Verify Docker Compose changes with `make compose-config`.
8. For runtime engine changes, run a small `evaluate` smoke test when feasible.
9. Do not commit generated outputs, local virtualenvs, caches, or nested git directories.
10. Preserve user changes and avoid unrelated refactors.

## Commands

Install and test:

```bash
make setup
make test
make compose-config
```

CLI help:

```bash
.venv/bin/python -m perfagent --help
```

HTTP evaluation:

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --engine k6 \
  --output ./outputs/sample-payments-api
```

Capacity mode:

```bash
.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --mode capacity \
  --fail-on BLOCK,UNKNOWN
```

Production traffic profile:

```bash
.venv/bin/python -m perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --traffic-profile production
```

Regression compare:

```bash
.venv/bin/python -m perfagent regression compare \
  --run-dir ./outputs/sample-payments-api \
  --db-path ./outputs/perfagent.db \
  --max-p95-regression-percent 20 \
  --max-error-rate-delta-percent 0.5 \
  --fail-on-regression
```

Prometheus validation:

```bash
.venv/bin/python -m perfagent prometheus validate \
  --prometheus-url http://localhost:9090 \
  --prometheus-service-label sample-payments-api \
  --prometheus-query-config ./examples/prometheus-queries.yaml
```

External result import:

```bash
.venv/bin/python -m perfagent import-results \
  --run-dir ./outputs/sample-payments-api \
  --tool locust \
  --result ./outputs/sample-payments-api/raw/locust_stats.csv \
  --service-name sample-payments-api \
  --runtime python \
  --target-url http://localhost:8080 \
  --slo-p95-ms 500 \
  --slo-error-rate 1
```

## Claude Usage

For Claude Code or Claude-style agents:

- Treat this file as the project memory.
- Read `skills/performance-engineer/SKILL.md` before performance work.
- Load only the matching reference file to avoid context bloat.
- When asked to implement, edit the repo directly and verify.
- When asked to review, lead with findings and file references.
- Keep final responses concise and evidence-backed.

Suggested prompt:

```text
Use SKILLS.md and skills/performance-engineer/SKILL.md as project context. Implement the requested PerfAgent change, preserve deterministic evidence generation, update tests/docs, and run verification.
```

## Gemini Usage

For Gemini CLI or Gemini-style agents:

- Use `SKILLS.md` as the global project instruction file.
- Use the skill pack references as task-local context.
- Prefer short, explicit implementation plans before broad edits.
- Do not generate speculative performance conclusions.
- If a metric is missing, state it as missing.

Suggested prompt:

```text
Read SKILLS.md, then use the relevant file under skills/performance-engineer/references. Make the code change in the existing PerfAgent style, add tests, and verify with make test.
```

## Codex Usage

For Codex:

- The project-local skill pack is not automatically loaded unless the agent reads it.
- Start with `skills/performance-engineer/SKILL.md` for performance-engineering work.
- Use `rg` for search and `apply_patch` for manual edits.
- Run tests and summarize verification.

Suggested prompt:

```text
Use the performance-engineer skill under skills/performance-engineer. Follow SKILLS.md and implement the requested PerfAgent feature end to end.
```

## MCP Direction

PerfAgent can be exposed through MCP as a standardized interface for agents and IDEs.

Potential MCP tools:

- `evaluate_service`
- `generate_test`
- `compare_regression`
- `query_runs`
- `validate_prometheus`
- `collect_traffic_profile`
- `generate_report`

MCP must call the same deterministic workflow used by the CLI. It should not create a separate source of truth.

## Quality Bar

A change is not complete unless:

- deterministic artifacts are generated or intentionally skipped
- reports still render
- tests cover the new behavior
- docs/examples match the actual command surface
- missing metrics and uncertainty are explicit
- the user can run the command from README/docs without hidden steps
