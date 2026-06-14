# CI Integration

PerfAgent is designed to be imported into CI as a containerized release-readiness step. The recommended CI shape is:

1. Build or pull the service under test.
2. Start the service and dependencies.
3. Wait for health.
4. Run `perfagent evaluate`.
5. Upload the output directory as a CI artifact.
6. Optionally fail the pipeline on `BLOCK`.

## GitHub Actions

Use [examples/ci/github-actions.yml](../examples/ci/github-actions.yml).

For a reusable workflow template that can be called from service repositories, use [examples/ci/github-actions-reusable.yml](../examples/ci/github-actions-reusable.yml).

Key command:

```bash
docker compose run --rm perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://host.docker.internal:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 10s \
  --output ./outputs/sample-payments-api
```

To publish a reusable PR comment body, generate Markdown after the run completes:

```bash
docker compose run --rm perfagent ci comment \
  --summary ./outputs/sample-payments-api/reports/summary.json \
  --output ./outputs/sample-payments-api/perfagent-pr-comment.md
```

GitHub Actions can post that file with `gh pr comment`, `actions/github-script`, or a standard PR-comment action. The command is intentionally separated from the GitHub API call so the same report body can be reused by GitLab, Jenkins, Buildkite, and local release gates.

## GitLab CI

Use [examples/ci/gitlab-ci.yml](../examples/ci/gitlab-ci.yml).

The example uses Docker-in-Docker and stores `outputs/sample-payments-api` as a job artifact.

## Jenkins

Use [examples/ci/Jenkinsfile](../examples/ci/Jenkinsfile).

The example archives the full PerfAgent output directory after every run.

## Failing A Pipeline On Release Decision

The CLI can fail directly on selected release decisions:

```bash
docker compose run --rm perfagent evaluate \
  --service-name sample-payments-api \
  --openapi ./examples/sample-payments-api/openapi.yaml \
  --target-url http://demo-http-payments:8080 \
  --runtime python \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 1m \
  --fail-on BLOCK,UNKNOWN \
  --output ./outputs/sample-payments-api
```

The release decision is also available in `reports/summary.json` if a pipeline needs custom policy logic:

```bash
decision="$(python - <<'PY'
import json
from pathlib import Path
summary = json.loads(Path("outputs/sample-payments-api/reports/summary.json").read_text())
print(summary["release_decision"])
PY
)"

if [ "$decision" = "BLOCK" ] || [ "$decision" = "UNKNOWN" ]; then
  echo "Performance gate failed: $decision"
  exit 1
fi
```

## Service Onboarding Checklist

- Add or generate an OpenAPI file for the service.
- Decide target URL for local, CI, and staging environments.
- Set p95 latency and error-rate SLOs.
- Add seed data or OpenAPI examples if business validation requires specific payloads.
- Add PerfAgent output directory to CI artifacts.
- Start with `WARN` as advisory, then promote `BLOCK` to a hard gate once the signal is trusted.
