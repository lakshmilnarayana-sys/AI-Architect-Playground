# Test Design

## Inputs To Capture

Capture these before generating a test:

- service name and owner
- protocol: HTTP, gRPC, WebSocket, browser UI, or mixed
- API contract: OpenAPI, proto, AsyncAPI, WebSocket message examples, UI journey definition
- target URL and deployment environment
- runtime and image tag
- service resources: CPU, memory, disk, replica count, limits, requests
- dependencies: databases, caches, queues, search, external APIs, internal upstream/downstream services
- auth mode and safe test credentials
- expected traffic: average RPS, peak RPS, endpoint mix, concurrency, message size, session length
- SLOs: p95/p99 latency, error rate, availability, throughput, recovery time
- test duration and ramp profile
- observability source and label mapping
- seed data or synthetic payload rules

If any item is missing, proceed with conservative defaults but mark the report with missing evidence.

## Workload Types

Baseline load:
- Represents expected production traffic or release gate traffic.
- Must pass for a `PASS` or `WARN` decision.
- If baseline fails, decision should be `BLOCK` unless evidence is missing.

Stress load:
- Exceeds expected load to find headroom.
- Failure here is usually `WARN` if baseline passes.
- Use for capacity planning and breakpoint discovery.

Capacity search:
- Steps through increasing RPS/concurrency until SLO breach.
- Reports estimated capacity as the highest observed RPS before the first sustained breach.
- Reports breaking point as the first RPS where p95 or error rate breaches SLO.

Recovery:
- Drops traffic after stress/capacity phase.
- Checks whether latency, errors, CPU, memory, queues, and dependency saturation recover.

Soak:
- Long-running stability test.
- Use after MVP for memory growth, connection leaks, cache growth, queue lag, and GC pressure.

Spike:
- Sudden increase in load.
- Use for burst tolerance and autoscaling response.

## Stage Design

Default HTTP MVP:

```yaml
phases:
  - name: warmup
    duration: 1m
    target_rps: 50
  - name: baseline
    duration: 5m
    target_rps: 200
  - name: stress
    duration: 5m
    target_rps: 500
  - name: recovery
    duration: 1m
    target_rps: 50
```

Capacity mode:

```yaml
phases:
  - name: warmup
    target_rps: 25
  - name: capacity_probe_50
    target_rps: 50
  - name: capacity_probe_100
    target_rps: 100
  - name: capacity_probe_200
    target_rps: 200
  - name: capacity_probe_400
    target_rps: 400
  - name: capacity_probe_800
    target_rps: 800
  - name: recovery
    target_rps: 25
```

Do not make stage durations so short that p95/p99 are statistically meaningless. A smoke run can be 10-30 seconds; a capacity claim should use enough samples per stage to be defensible.

## Payload Rules

Generate valid, safe, deterministic payloads:

- Respect required fields.
- Prefer OpenAPI examples/defaults/enums before generic values.
- Avoid real PII.
- Use stable test prefixes such as `cust_test_1001`.
- Keep IDs deterministic with seed input where possible.
- Generate path and query params separately from body.
- Preserve content type and required headers.
- Include auth placeholders but do not hard-code secrets.

Flag these as risks:

- business-rule validation cannot be inferred from schema
- endpoint needs pre-existing state
- idempotency rules are unknown
- generated data may collide
- write endpoints may mutate shared environments
- delete endpoints are unsafe without test isolation

## SLO And Decision Logic

Use deterministic logic:

- `PASS`: baseline and stress stay within latency/error SLO and no major saturation.
- `WARN`: baseline passes but stress/capacity breaches SLO, or headroom is limited.
- `BLOCK`: baseline breaches SLO, expected-load error rate exceeds SLO, or service is unstable.
- `UNKNOWN`: test did not execute, required metrics are missing, or evidence is insufficient.

Always include:

- target p95 and observed max p95
- target error rate and observed max error rate
- stable RPS
- peak RPS
- breaking point RPS if available
- first SLO breach timestamp and phase
- missing metrics

## Anti-Patterns

- Calling a single short smoke run "capacity".
- Using average latency instead of p95/p99 for user-facing SLOs.
- Ignoring failed checks because latency looks good.
- Mixing client-side errors and server-side 5xx without separating causes.
- Claiming dependency bottleneck without dependency metrics.
- Comparing two runs from different environments as a regression.
- Running destructive endpoints against shared production-like data without isolation.
