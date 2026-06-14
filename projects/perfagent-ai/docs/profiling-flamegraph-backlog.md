# Profiling And Flame Graph Backlog

## Current State

PerfAgent supports profiling artifact attachment:

```bash
perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://localhost:8080 \
  --runtime go \
  --slo-p95-ms 500 \
  --slo-error-rate 1 \
  --profile ./profiles/cpu.pprof \
  --profile ./profiles/heap.pprof \
  --output ./outputs/payments-api
```

The framework copies supplied files into `raw/profiles/`, lists them in `reports/report.md`, and exposes them in `reports/report.html`.

The profiling collector also emits deterministic `profiling_summary.json`-style metadata in the run state and `raw/profiling_artifacts.json`:

```json
{
  "profiles": [
    {
      "source_path": "./profiles/cpu.pprof",
      "artifact_path": "raw/profiles/cpu.pprof",
      "type": "pprof",
      "render_status": "not_rendered",
      "warnings": ["Rendering is not implemented for pprof profiles yet."]
    }
  ]
}
```

Attached SVG profile artifacts are classified as `flamegraph` with `render_status: "provided"` so reports and downstream processors can surface them as already-rendered artifacts.

PerfAgent can also create a deterministic eBPF/system profiler capture plan:

```bash
perfagent profile plan \
  --runtime go \
  --mode ebpf \
  --pid 12345 \
  --duration-seconds 60 \
  --output-json ./outputs/profile-plan.json
```

The default plan is language-independent and includes Linux perf/eBPF, bpftrace, Pyroscope eBPF, and Parca Agent options when the required local tools and target details are available. Runtime-specific commands for Go pprof, JVM/JFR, py-spy, and Node.js/Clinic.js remain available with `--mode runtime`.

PerfAgent can execute those commands explicitly:

```bash
perfagent profile run \
  --runtime go \
  --mode ebpf \
  --pid 12345 \
  --duration-seconds 60 \
  --output-json ./outputs/profile-result.json
```

PerfAgent can also run capture-phase commands during an evaluation with `evaluate --profile-auto`.

When Linux `perf` is available, PerfAgent captures `perf.data`, converts `perf script` output into `perf.folded`, renders `perf-flamegraph.svg`, and extracts top functions from the generated stack evidence. See [eBPF Profiling Setup](ebpf-profiling.md).

Remaining backlog work is phase-window correlation, richer runtime-specific profile interpretation, allocation hot spots, and embedded interactive profile viewers.

## What Users Can See Today

Today the report can show:

- profile file paths
- profile artifact names
- profile warnings for missing files
- attached runtime artifacts such as `.pprof`, `.jfr`, `py-spy`, Clinic.js, collapsed stacks, and Speedscope files
- structured profile entries with source path, copied artifact path, detected type, render status, and per-profile warnings
- supplied SVG flame graph artifacts as visible profiling entries
- generated eBPF artifacts such as `perf.data`, `perf.script`, `perf.folded`, and `perf-flamegraph.svg`
- top functions parsed from collapsed stacks, Speedscope files, simple text profiles, and `perf script`

Today the report does not yet embed:

- SVG flame graphs directly in report pages
- interactive Speedscope iframe/viewer
- allocation hot spots
- thread or goroutine breakdown
- GC pause analysis
- event loop delay analysis

## Backlog: Built-In Profiling

### P0: Profiling Artifact Contract

Add `processed/profiling_summary.json` as a durable processed artifact. The collector now emits the same core shape in memory and `raw/profiling_artifacts.json`; the remaining work is to write the processed copy and have reports consume the structured fields directly.

```json
{
  "runtime": "go",
  "profiles": [
    {
      "type": "cpu",
      "source_path": "raw/profiles/cpu.pprof",
      "flamegraph_path": "reports/assets/cpu-flamegraph.svg",
      "speedscope_path": "reports/assets/cpu.speedscope.json",
      "top_functions": [
        {"name": "AuthorizePayment", "flat_percent": 18.2, "cum_percent": 44.1}
      ],
      "warnings": []
    }
  ]
}
```

Acceptance criteria:

- profile summary is generated for every attached profile: complete in collector output
- report links to raw profile and rendered flame graph when available: raw artifact links exist; structured flame graph rendering is pending
- missing parser/converter emits warnings, not false conclusions

### P1: Go Profiling

Capture:

- CPU profile
- heap profile
- goroutine profile
- block profile
- mutex profile

Inputs:

- `--runtime go`
- `--profile-endpoint http://service:6060/debug/pprof`
- test start/end timestamps

Commands to support:

```bash
go tool pprof -proto http://service:6060/debug/pprof/profile?seconds=30
go tool pprof -svg cpu.pprof
go tool pprof -top cpu.pprof
```

Report sections:

- CPU flame graph
- top flat CPU functions
- top cumulative CPU functions
- heap allocation hot spots
- goroutine count and blocked goroutines

### P1: Java Profiling

Capture:

- JFR recording
- GC logs
- thread dumps
- heap histogram

Inputs:

- Java process id or container name
- JDK tooling availability
- JFR duration aligned to stress window

Commands to support:

```bash
jcmd <pid> JFR.start name=perfagent settings=profile duration=60s filename=/tmp/perfagent.jfr
jcmd <pid> Thread.print
jcmd <pid> GC.class_histogram
```

Report sections:

- JFR file link
- GC pause summary
- allocation hot classes
- blocked threads
- lock contention

### P1: Python Profiling

Capture:

- py-spy CPU profile
- speedscope JSON
- native stack summary if available

Commands to support:

```bash
py-spy record --pid <pid> --duration 60 --format speedscope --output py-spy.speedscope.json
py-spy top --pid <pid>
```

Report sections:

- Speedscope link
- hottest Python functions
- time in native extensions
- thread activity

### P1: Node.js Profiling

Capture:

- V8 CPU profile
- heap snapshot
- event loop delay
- Clinic.js profile when available

Commands/tools to support:

```bash
clinic flame -- node server.js
node --cpu-prof server.js
node --heap-prof server.js
```

Report sections:

- CPU flame graph or Clinic artifact
- event loop delay summary
- heap growth summary
- top JavaScript functions

### P2: Container And Kubernetes Profiling

Support:

- Docker container PID discovery
- Kubernetes pod/container selection
- ephemeral debug containers where permitted
- profile capture during a specific test phase

Inputs:

- namespace
- deployment/pod selector
- container name
- profile duration
- profiling permission mode

Example future CLI:

```bash
perfagent evaluate \
  --service-name payments-api \
  --openapi ./openapi.yaml \
  --target-url http://payments-api:8080 \
  --runtime go \
  --profile-mode auto \
  --profile-target kubernetes \
  --profile-namespace payments \
  --profile-selector app=payments-api \
  --profile-phase stress
```

### P2: Report Rendering

Add `reports/assets/` with:

- `cpu-flamegraph.svg`
- `heap-flamegraph.svg`
- `profile.speedscope.json`
- `top-functions.json`

Interactive report should show:

- flame graph tab
- profile type selector
- top functions table
- links to raw profile files
- warnings when profile data is missing
- correlation between first SLO breach and profile capture window

### P2: Reasoning Integration

The ReAct reasoning loop should get structured profile summaries, not raw flame graph files.

Tool observations:

- `inspect_cpu_profile`
- `inspect_heap_profile`
- `inspect_thread_or_goroutine_profile`
- `inspect_gc_or_runtime_pauses`
- `inspect_profile_test_window_alignment`

Rules:

- Profiles can increase confidence in CPU, memory, lock, GC, or event-loop bottlenecks.
- Profiles cannot decide release status.
- Profiles cannot override SLO or regression math.

## Deterministic Profiling Rules

PerfAgent should only cite profiling evidence when:

- profile capture overlaps the test phase being analyzed
- runtime and profile type are known
- top-function percentages are parsed deterministically
- raw artifact path is preserved
- conversion warnings are included

## Priority

1. Generate `profiling_summary.json` from attached profiles.
2. Render SVG/Speedscope flame graph links in HTML report.
3. Add Go pprof capture and `go tool pprof -top/-svg` parsing.
4. Add py-spy Speedscope capture.
5. Add Java JFR summary capture.
6. Add Node.js Clinic/V8 profile support.
7. Correlate profile windows with SLO breach windows.
