# Onboarding An HTTP Service

This guide shows how to onboard a new HTTP microservice to PerfAgent.

## 1. Add The OpenAPI Contract

Place the service contract somewhere stable:

```text
services/payments-api/openapi.yaml
```

The MVP needs:

- Paths and HTTP methods
- Request body schemas
- Required fields
- Required headers
- Path/query parameters
- 2xx response codes

## 2. Pick Initial SLOs

Start with explicit service-owner SLOs:

```text
p95 latency: 500 ms
error rate: 1%
```

If the team does not have SLOs yet, use a non-blocking CI run first and review the generated baseline.

## 3. Run A Local Evaluation

```bash
.venv/bin/python -m perfagent evaluate \
  --service-name payments-api \
  --openapi ./services/payments-api/openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --duration 1m \
  --output ./outputs/payments-api
```

## 4. Review Artifacts

Inspect:

- `generated/perf_test.js`
- `processed/features.json`
- `processed/bottleneck_analysis.json`
- `reports/report.html`

## 5. Add To CI

Use one of:

- [GitHub Actions](../../examples/ci/github-actions.yml)
- [GitLab CI](../../examples/ci/gitlab-ci.yml)
- [Jenkins](../../examples/ci/Jenkinsfile)

## 6. Promote The Gate

Recommended adoption path:

1. Run PerfAgent as advisory and upload reports.
2. Fail only on `UNKNOWN`, because missing evidence means the test is broken.
3. Fail on `BLOCK` after two or three stable baseline runs.
4. Use `WARN` for PR comments or release review until expected headroom is agreed.
