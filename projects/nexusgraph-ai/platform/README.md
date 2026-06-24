# StreamFlix Platform (Phase 1)

Local kind cluster running the StreamFlix service topology (generated from
`../graph/*.csv`) with Prometheus/Grafana/Loki/Tempo and runtime fault injection.

## Quickstart

```bash
cd platform
make up        # kind cluster + local registry
make build     # build & push service + loadgen images
make observe   # install observability stack (several minutes)
make deploy    # generate manifests from graph + apply apps + loadgen
make verify
```

Grafana: `kubectl --context kind-streamflix -n observability port-forward svc/kps-grafana 3000:80` → http://localhost:3000 (admin/admin).

## Fault injection

```bash
make fault SVC=playback MODE=cpu_throttle VALUE=2 TTL=120
make fault SVC=playback MODE=clear
```

Modes reproducible at runtime: `cpu_throttle`, `memory_leak`, `oom_kill`, `pod_restart`, `disk_iops`.
Manifest-layer modes: `image_pull_backoff` (apply `cluster/variants/playback-imagepull.yaml`), `hpa_maxed`/`node_pressure` (Phase 2, best-effort on a laptop).

### Fault catalog

| Mode | Mechanism | Observable signal |
|------|-----------|------------------|
| `cpu_throttle` | Spin goroutines consuming VALUE cores | p95 latency spike in Prometheus / Grafana |
| `memory_leak` | Allocate VALUE MiB and hold | RSS growth; eventually OOM |
| `oom_kill` | Allocate 8 MiB per call, hold | Pod `OOMKilled` when memory limit (128Mi) is breached |
| `pod_restart` | `os.Exit(1)` after TTL seconds | Deployment restarts visible in `kubectl get pods` |
| `disk_iops` | Write-loop to a temp file at VALUE MB/s | Disk I/O saturation (best-effort on a laptop) |
| `image_pull_backoff` | Patch deployment to a nonexistent image tag | Pod enters `ImagePullBackOff` / `ErrImagePull` |
| `clear` | Clear all active faults | Service returns to baseline behaviour |

## Teardown

```bash
make down
```
