# Continuous Performance

PerfAgent can persist every execution in a local SQLite database and use that history for regression detection.

Default storage:

```yaml
storage:
  enabled: true
  backend: sqlite
  path: ./outputs/perfagent.db
  retention_days: 30
```

Shared CI storage can use Postgres:

```yaml
storage:
  enabled: true
  backend: postgres
  dsn_env: PERFAGENT_DATABASE_URL
  retention_days: 30
```

Every `evaluate` run records:

- run ID
- service name
- created timestamp
- release decision
- stable RPS
- max p95 latency
- max error rate
- report path
- feature JSON

Manage retained runs:

```bash
.venv/bin/python -m perfagent storage list \
  --db-path ./outputs/perfagent.db \
  --service-name payments-api

.venv/bin/python -m perfagent storage retention \
  --db-path ./outputs/perfagent.db \
  --retention-days 30
```

Compare a run against the latest stored baseline:

```bash
.venv/bin/python -m perfagent regression compare \
  --run-dir ./outputs/payments-api \
  --db-path ./outputs/perfagent.db \
  --max-p95-regression-percent 20 \
  --max-error-rate-delta-percent 0.5 \
  --fail-on-regression
```

## PR Complexity Triggering

PerfAgent includes a PR complexity helper that classifies changed files:

- `smoke`: docs or low-risk changes
- `targeted`: service code or runtime changes
- `full-regression`: DB migrations, dependency changes, infra/runtime changes, or high-risk service changes

Example GitHub Actions logic:

```yaml
name: continuous-performance

on:
  pull_request:
  schedule:
    - cron: "0 2 * * *"   # nightly
    - cron: "0 3 * * 0"   # weekly

jobs:
  perfagent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e '.[dev]'
      - name: Select performance profile
        run: |
          git diff --name-only origin/main...HEAD > changed-files.txt
          python - <<'PY'
          from perfagent.ci.pr_complexity import classify_pr_complexity
          files = open("changed-files.txt").read().splitlines()
          result = classify_pr_complexity(files)
          print(result)
          open("perf-profile.txt", "w").write(result["recommended_profile"])
          PY
      - name: Run PerfAgent
        run: |
          PROFILE=$(cat perf-profile.txt)
          if [ "$PROFILE" = "full-regression" ]; then
            MODE=capacity
            DURATION=10m
          elif [ "$PROFILE" = "targeted" ]; then
            MODE=standard
            DURATION=3m
          else
            MODE=standard
            DURATION=30s
          fi
          perfagent evaluate \
            --config ./examples/sample-config.yaml \
            --mode "$MODE" \
            --duration "$DURATION" \
            --fail-on BLOCK,UNKNOWN
      - uses: actions/upload-artifact@v4
        with:
          name: perfagent-report
          path: outputs/**/*
```

## Nightly and Weekly Runs

Recommended schedule:

- PR smoke or targeted run based on complexity
- nightly production-like traffic profile run
- weekly full capacity/regression run

Nightly:

```bash
perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --traffic-profile production \
  --fail-on BLOCK
```

Weekly:

```bash
perfagent evaluate \
  --config ./examples/sample-config.yaml \
  --mode capacity \
  --traffic-profile production \
  --fail-on BLOCK,WARN,UNKNOWN
```

## Database Backends

SQLite is the default local backend. Postgres is available for multi-runner or shared CI deployments through the optional `perfagent-ai[postgres]` dependency.
