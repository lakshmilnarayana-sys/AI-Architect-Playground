# StreamFlix Software Catalog (Phase 4 — Backstage)

A real Backstage catalog whose entities are generated from `../../graph/*.csv`
(1 System, 13 Groups, 12 Users, 35 Components with dependsOn/ownedBy +
Prometheus/runbook annotations). "The catalog IS the graph."

## Deploy

```bash
cd platform
make backstage        # generate catalog → ConfigMap → build+load image → deploy to ns backstage
make backstage-up     # port-forward 7007 + print URL
make backstage-verify
```

Open `http://localhost:7007` for the UI; the catalog API is at
`http://localhost:7007/api/catalog/entities`.

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

This deployment serves the catalog API via a lightweight catalog-server; the full
Backstage UI build was deferred — see the Phase 4 spec risk note.
