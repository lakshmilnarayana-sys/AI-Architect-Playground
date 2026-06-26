# StreamFlix Software Catalog (Phase 4 — Backstage)

A software catalog (Backstage entity model) whose entities are generated from
`../../graph/*.csv` (1 System, 13 Groups, 12 Users, 35 Components with dependsOn/ownedBy +
Prometheus/runbook annotations). "The catalog IS the graph."

> **What is deployed:** a queryable **catalog API** (`/api/catalog/entities`) served by a
> lightweight Go `catalog-server`. The full **Backstage UI is NOT delivered** — the real
> Backstage in-container build was infeasible in this environment (host Node 25 / no yarn;
> create-app interactivity + Yarn 4 strict lockfile). This is the spec §8 documented
> fallback serving the *same* generated entities. The committed `Dockerfile` +
> `app-config.yaml` are the deferred primary Backstage path (not currently built); the
> built image is `catalog-server/`.

## Deploy

```bash
cd platform
make backstage        # generate catalog → ConfigMap → build+load image → deploy to ns backstage
make backstage-up     # port-forward 7007 + print URL
make backstage-verify
```

The catalog API is at `http://localhost:7007/api/catalog/entities` (no browsable UI in the
fallback — query the API directly).

## Verify

```bash
curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=component' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),"components")'   # 35
```

## Regenerate after a graph change

`make backstage` always regenerates the catalog from the graph before deploying, so
the catalog never drifts from `graph/`.

## Notes

SQLite + guest auth (local demo). Component names match the running k8s services
(`<short>-service`). Owners come from `OWNS_SERVICE`; unowned imported services default
to `group:platform-engineering`. Runbook links point at `platform/runbooks/*.md`.
