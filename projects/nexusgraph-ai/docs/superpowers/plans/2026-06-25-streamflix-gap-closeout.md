# StreamFlix Phase 1–2 Gap Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the known gaps in the built StreamFlix platform: wire OpenTelemetry trace export so request fan-out is visible in Tempo (Phase 1 acceptance criterion #3), plus four small cleanups.

**Architecture:** Add the OTel Go SDK to the single parameterized service: a tracer provider exporting OTLP/HTTP to the already-deployed Tempo (`tempo.observability.svc:4318`), an `otelhttp`-wrapped server handler, and an `otelhttp`-wrapped downstream client that propagates W3C trace context — so a `playback` request and its fan-out to `manifest`/`cdn-routing`/`recommendation`/`identity` form one linked trace. The manifest generator injects `OTEL_EXPORTER_OTLP_ENDPOINT` and normalizes the junk `SERVICE_TIER`. Two config cleanups (container-level memory alert, stale `alerting.py` comment) round it out.

**Tech Stack:** Go 1.22 (OTel SDK: otlptracehttp, sdk/trace, contrib otelhttp), Python generator, Tempo (OTLP), kind, kubectl.

## Global Constraints

- Cluster `kind` named `streamflix`, context `kind-streamflix`. Every kubectl passes `--context kind-streamflix`. NEVER target `*-prod` EKS.
- Apps in `streamflix-prod`; Tempo/observability in `observability`. Tempo OTLP/HTTP endpoint: `tempo.observability.svc:4318` (no separate OTel Collector — Tempo receives OTLP directly).
- Service image `localhost:5001/streamflix-service:dev`. All code under `platform/`.
- OTel resource `service.name` MUST equal the service's `SERVICE_NAME` env (e.g. `playback-service`), consistent with the Prometheus `service` label so traces and metrics correlate.
- Commit author `lakshminarayana-sys`, signed, no Claude trailer: `git -c user.name=lakshminarayana-sys commit -m "..."`. Repo root `/Users/lnv/Documents/maven`; stage only each task's files; never `git add -A`.
- Run go/docker from `platform/services/streamflix-service` or `platform/`. Local Go 1.26 available; module proxy reachable (Phase 1 fetched deps fine).

---

### Task 1: OpenTelemetry tracing + real disk_iops in the Go service

**Files:**
- Modify: `platform/services/streamflix-service/main.go`
- Create: `platform/services/streamflix-service/tracing.go`
- Modify: `platform/services/streamflix-service/go.mod` (+ `go.sum` via tidy)
- Create: `platform/services/streamflix-service/tracing_test.go`

**Interfaces:**
- Produces: `initTracer(ctx context.Context, serviceName, endpoint string) (shutdown func(context.Context) error, err error)` in `tracing.go`. `main.go` wraps the mux with `otelhttp.NewHandler` and uses an `otelhttp.NewTransport` client whose downstream requests are built with `http.NewRequestWithContext(r.Context(), ...)`.
- `disk_iops` fault performs real bounded file I/O (not just latency).

- [ ] **Step 1: Add OTel deps to go.mod**

Run (populates go.mod + go.sum):
```bash
cd platform/services/streamflix-service
go get go.opentelemetry.io/otel@v1.28.0 \
  go.opentelemetry.io/otel/sdk@v1.28.0 \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.28.0 \
  go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@v0.53.0
```
Expected: go.mod lists the four modules; go.sum updated. (If v1.28.0/v0.53.0 are unavailable, use the latest compatible 1.x/0.x the proxy serves and note it.)

- [ ] **Step 2: Write the failing test `tracing_test.go`**

```go
package main

import (
	"context"
	"testing"
)

func TestInitTracerReturnsShutdown(t *testing.T) {
	// endpoint need not be reachable; exporter creation is lazy/batched.
	shutdown, err := initTracer(context.Background(), "test-service", "localhost:4318")
	if err != nil {
		t.Fatalf("initTracer error: %v", err)
	}
	if shutdown == nil {
		t.Fatal("expected non-nil shutdown func")
	}
	_ = shutdown(context.Background())
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd platform/services/streamflix-service && go test ./... 2>&1 | head`
Expected: FAIL — `undefined: initTracer`.

- [ ] **Step 4: Write `tracing.go`**

```go
package main

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// initTracer configures an OTLP/HTTP exporter to Tempo and installs a global
// tracer provider + W3C propagator. Returns a shutdown func to flush spans.
func initTracer(ctx context.Context, serviceName, endpoint string) (func(context.Context) error, error) {
	exp, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint(endpoint), // host:port, no scheme
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}
	res, err := resource.New(ctx, resource.WithAttributes(semconv.ServiceName(serviceName)))
	if err != nil {
		return nil, err
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{},
	))
	return tp.Shutdown, nil
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd platform/services/streamflix-service && go test ./...`
Expected: PASS.

- [ ] **Step 6: Wire tracing + context propagation + real disk_iops into `main.go`**

Changes (apply all):

(a) Imports — add:
```go
	"context"
	"os"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
```
(`context` and `os` are already imported — keep one copy.)

(b) In `main()`, before building the mux, init the tracer (default endpoint to Tempo):
```go
	otlpEndpoint := env("OTEL_EXPORTER_OTLP_ENDPOINT", "tempo.observability.svc:4318")
	if shutdown, err := initTracer(context.Background(), svcName, otlpEndpoint); err != nil {
		log.Printf("tracing disabled: %v", err)
	} else {
		defer shutdown(context.Background())
	}
```

(c) Wrap the mux handler so every request is a server span:
```go
	addr := ":" + env("PORT", "8080")
	log.Printf("%s (%s) listening on %s", svcName, svcTier, addr)
	log.Fatal(http.ListenAndServe(addr, otelhttp.NewHandler(mux, "http.server")))
```

(d) Make the downstream client propagate trace context. Replace the existing downstream client + `client.Get(url)` loop in `handleRoot` with a context-propagating transport and per-request context:
```go
	client := &http.Client{Timeout: 2 * time.Second, Transport: otelhttp.NewTransport(http.DefaultTransport)}
	for name, url := range downstreams() {
		req, _ := http.NewRequestWithContext(r.Context(), http.MethodGet, url, nil)
		resp, err := client.Do(req)
		dc := "error"
		if err == nil {
			dc = strconv.Itoa(resp.StatusCode)
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
		}
		down.WithLabelValues(name, dc).Inc()
	}
```

(e) Real `disk_iops` fault — replace the `case "disk_iops":` body in `applyFault` so it does bounded real file I/O (write+sync+remove a small temp file `value` times), then still returns a small latency to reflect I/O cost:
```go
	case "disk_iops":
		n := int(val)
		if n < 1 {
			n = 1
		}
		if n > 50 {
			n = 50 // bounded: never hammer a laptop disk
		}
		buf := make([]byte, 1024*1024) // 1 MiB
		for i := 0; i < n; i++ {
			f, err := os.CreateTemp("", "perf-iops-*")
			if err != nil {
				break
			}
			f.Write(buf)
			f.Sync()
			f.Close()
			os.Remove(f.Name())
		}
		return time.Duration(n*5) * time.Millisecond, false
```

- [ ] **Step 7: Build + test**

Run:
```bash
cd platform/services/streamflix-service
go mod tidy
go vet ./... && go test ./...
docker build -t localhost:5001/streamflix-service:dev .
```
Expected: vet clean, tests PASS, image builds (the Dockerfile's `COPY go.mod ./` + `go mod download` now pulls OTel deps; if the build needs `go.sum`, ensure the Dockerfile copies it — see Step 8).

- [ ] **Step 8: Ensure the Dockerfile copies go.sum**

Confirm `platform/services/streamflix-service/Dockerfile` copies `go.sum` before build. If the line is `COPY go.mod ./`, change it to `COPY go.mod go.sum ./`. (If go.sum did not exist before, `go mod tidy` in Step 7 created it.) Rebuild to confirm.

- [ ] **Step 9: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/services/streamflix-service
git -c user.name=lakshminarayana-sys commit -m "feat(platform): OTel trace export + context propagation + real disk_iops"
```

---

### Task 2: Generator — inject OTLP endpoint + normalize SERVICE_TIER

**Files:**
- Modify: `platform/scripts/generate_manifests.py`
- Modify: `platform/scripts/test_generate_manifests.py`

**Interfaces:**
- Consumes: graph CSVs.
- Produces: each generated Deployment sets `OTEL_EXPORTER_OTLP_ENDPOINT=tempo.observability.svc:4318`; `SERVICE_TIER` is normalized to `customer-facing` or `internal` (junk import descriptions no longer leak into the env value).

- [ ] **Step 1: Write failing tests in `test_generate_manifests.py`**

```python
def test_render_service_sets_otel_endpoint():
    svc = {"id": "service:playback", "short": "playback", "tier": "customer-facing"}
    out = render_service(svc, [], "img:dev")
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in out
    assert "tempo.observability.svc:4318" in out

def test_service_tier_normalized():
    from generate_manifests import _normalize_tier
    assert _normalize_tier("customer-facing") == "customer-facing"
    assert _normalize_tier("internal") == "internal"
    assert _normalize_tier("Imported from Netflix synthetic dataset: Service account-service") == "internal"
    assert _normalize_tier("") == "internal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd platform/scripts && python -m pytest test_generate_manifests.py -k "otel or tier" -v 2>&1 | head`
Expected: FAIL (`OTEL_EXPORTER_OTLP_ENDPOINT` absent; `_normalize_tier` undefined).

- [ ] **Step 3: Implement in `generate_manifests.py`**

(a) Add helper near `_safe_label`:
```python
def _normalize_tier(tier: str) -> str:
    """Collapse arbitrary descriptions to a valid tier; default to internal."""
    t = (tier or "").strip().lower()
    return t if t in ("customer-facing", "internal") else "internal"
```

(b) In `render_service`, compute `tier = _normalize_tier(svc["tier"])` and use `tier` for BOTH the `SERVICE_TIER` env value and the `tier` label (replace the prior `svc['tier']` / `_safe_label(svc['tier'])` usages with `tier` / `_safe_label(tier)`).

(c) Add the OTel env var to the container `env` list (after `ERROR_RATE`):
```yaml
            - {{name: OTEL_EXPORTER_OTLP_ENDPOINT, value: "tempo.observability.svc:4318"}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd platform/scripts && python -m pytest test_generate_manifests.py -v`
Expected: PASS (all prior tests + the 2 new ones).

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/scripts/generate_manifests.py projects/nexusgraph-ai/platform/scripts/test_generate_manifests.py
git -c user.name=lakshminarayana-sys commit -m "feat(platform): generator injects OTLP endpoint + normalizes SERVICE_TIER"
```

---

### Task 3: Config cleanups — container-level memory alert + alerting.py metric name

**Files:**
- Modify: `platform/alerting/rules/streamflix-alerts.yaml`
- Modify: `src/incident/alerting.py`

**Interfaces:**
- Produces: `StreamFlixMemoryNearLimit` aggregates by `(pod, container)`; `alerting.py` `oom_kill` metric string matches the working kube-state-metrics name.

- [ ] **Step 1: Fix the memory alert aggregation**

In `platform/alerting/rules/streamflix-alerts.yaml`, change the `StreamFlixMemoryNearLimit` expr from `sum by (pod)` to `sum by (pod, container)` in BOTH numerator and denominator:
```yaml
          expr: |
            sum by (pod, container) (container_memory_working_set_bytes{namespace="streamflix-prod", container!=""})
              / sum by (pod, container) (kube_pod_container_resource_limits{namespace="streamflix-prod", resource="memory"}) > 0.9
```

- [ ] **Step 2: Fix the stale metric name in `alerting.py`**

In `src/incident/alerting.py`, the `oom_kill` entry's `metric` reads `kube_pod_container_status_terminated_reason`. Change it to the working name `kube_pod_container_status_last_terminated_reason` (matches the live PrometheusRule). Change ONLY that string; leave the threshold text and all other entries untouched.

- [ ] **Step 3: Validate both files**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai
python3 -c "import yaml; d=yaml.safe_load(open('platform/alerting/rules/streamflix-alerts.yaml')); m=[r for g in d['spec']['groups'] for r in g['rules'] if r['alert']=='StreamFlixMemoryNearLimit'][0]; assert 'sum by (pod, container)' in m['expr']; print('memory alert OK')"
python3 -c "import ast,re; s=open('src/incident/alerting.py').read(); assert 'kube_pod_container_status_last_terminated_reason' in s; print('alerting.py OK')"
```
Expected: both print OK.

- [ ] **Step 4: Apply the updated rule live and confirm it loads**

Run:
```bash
kubectl --context kind-streamflix apply -f platform/alerting/rules/streamflix-alerts.yaml
kubectl --context kind-streamflix -n observability get prometheusrule streamflix-alerts
```
Expected: rule applied (configured). (Operator reload picks up the new expr.)

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/alerting/rules/streamflix-alerts.yaml projects/nexusgraph-ai/src/incident/alerting.py
git -c user.name=lakshminarayana-sys commit -m "fix(platform): container-level memory alert + align alerting.py oom metric name"
```

---

### Task 4: Rebuild, redeploy, and verify trace fan-out in Tempo (acceptance)

**Files:**
- Modify: `platform/Makefile` (add `traces-verify` target)

**Interfaces:**
- Consumes: new service image (Task 1), generator changes (Task 2).
- Produces: redeployed services emitting traces; `make traces-verify`; documented proof that a `playback` trace shows downstream fan-out (Phase 1 acceptance criterion #3).

- [ ] **Step 1: Add `traces-verify` to `platform/Makefile`**

```makefile
.PHONY: traces-verify
traces-verify:
	@echo "Port-forward Tempo then query a recent playback trace:"
	@echo "  kubectl --context $(CTX) -n observability port-forward svc/tempo 3200:3200"
	@echo "  curl -s 'http://localhost:3200/api/search?tags=service.name=playback-service&limit=1'"
	@echo "Then GET /api/traces/<traceID> and confirm multiple service.name values (fan-out)."
```

- [ ] **Step 2: Rebuild, load, regenerate, redeploy all services**

Run:
```bash
cd platform
make build
kind load docker-image localhost:5001/streamflix-service:dev --name streamflix
python3 scripts/generate_manifests.py --out cluster/generated --nodes ../graph/nodes.csv --edges ../graph/edges.csv
kubectl --context kind-streamflix apply -f cluster/generated/
kubectl --context kind-streamflix -n streamflix-prod rollout restart deployment
kubectl --context kind-streamflix -n streamflix-prod rollout status deploy/playback-service --timeout=180s
```
Expected: all deployments roll to the new image; playback-service Ready. (loadgen keeps driving traffic.)

- [ ] **Step 3: Verify SERVICE_TIER is clean on an imported service**

Run:
```bash
kubectl --context kind-streamflix -n streamflix-prod get deploy account-service-service -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="SERVICE_TIER")]}{.value}{"\n"}{end}' 2>/dev/null
```
Expected: `internal` (NOT the junk "Imported from Netflix..." string).

- [ ] **Step 4: ACCEPTANCE — trace fan-out visible in Tempo (run for real)**

Run:
```bash
kubectl --context kind-streamflix -n observability port-forward svc/tempo 3200:3200 >/tmp/pf-tempo.log 2>&1 &
sleep 5
# wait for traces to accumulate from loadgen hitting playback
sleep 30
TRACE=$(curl -s 'http://localhost:3200/api/search?tags=service.name%3Dplayback-service&limit=1' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['traces'][0]['traceID'] if d.get('traces') else '')")
echo "traceID=$TRACE"
curl -s "http://localhost:3200/api/traces/$TRACE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
svcs=set()
for b in d.get('batches', []):
    for attr in b.get('resource', {}).get('attributes', []):
        if attr['key']=='service.name':
            svcs.add(attr['value'].get('stringValue'))
print('services in trace:', sorted(svcs))
assert len(svcs) >= 2, 'expected fan-out across >=2 services'
print('FAN-OUT CONFIRMED')
"
kill %1 2>/dev/null
```
Expected: the trace contains `playback-service` plus at least one downstream (`manifest-service`/`cdn-routing-service`/`recommendation-service`/`identity-service`) — `FAN-OUT CONFIRMED`. Capture the `services in trace` line. (Tempo search/ingest can lag ~30-60s; poll if the first query is empty.)

- [ ] **Step 5: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/Makefile
git -c user.name=lakshminarayana-sys commit -m "feat(platform): traces-verify target + verified Tempo trace fan-out"
```

---

## Done = acceptance

1. Service emits OTel traces; a `playback` request trace shows downstream fan-out in Tempo (Phase 1 criterion #3). (Task 4 Step 4)
2. `disk_iops` does real bounded file I/O. (Task 1)
3. Generated deployments set `OTEL_EXPORTER_OTLP_ENDPOINT`; `SERVICE_TIER` normalized (no junk strings). (Task 2, Task 4 Step 3)
4. `StreamFlixMemoryNearLimit` aggregates per container; `alerting.py` oom metric name aligned. (Task 3)

## Self-review notes

- **Coverage:** OTel traces (T1+T4 — the headline gap), real disk_iops (T1), OTLP env + tier normalization (T2), memory alert + alerting.py (T3), live trace fan-out acceptance (T4). All four chosen gaps covered.
- **Type/name consistency:** `initTracer(ctx, serviceName, endpoint)` defined T1, used T1 main.go. `_normalize_tier` defined+used T2. `OTEL_EXPORTER_OTLP_ENDPOINT` value `tempo.observability.svc:4318` consistent across T1 default, T2 generator, and the live Tempo OTLP/HTTP port 4318.
- **Honesty flag:** OTel dep versions (v1.28.0/v0.53.0) are best-known-good; if the proxy serves different compatible versions the implementer uses those and notes it. Trace export is batched, so initTracer succeeds even if Tempo is unreachable at boot (no crash); the live acceptance (T4) is the real proof.
- **Risk:** redeploying all 35 services via rollout restart re-pulls the kind-loaded image; playback fan-out depends on its DEPENDS_ON downstreams running (they are, 36/36).
