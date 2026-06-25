# StreamFlix Platform Phase 4 — Backstage Software Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stand up a real Backstage software catalog on the kind cluster whose entities (System, Groups, Users, Components with dependsOn/ownedBy + Prometheus/runbook annotations) are generated from the same `graph/` CSVs that drive the platform.

**Architecture:** A Python generator renders Backstage entity YAML from `graph/{nodes,edges}.csv` into `platform/backstage/catalog/catalog.yaml`. A real Backstage app, built entirely inside a `node:20` multi-stage Docker image (host has Node 25 + no yarn), with SQLite + guest auth, ingests the catalog via a mounted ConfigMap and serves the catalog API. If the heavyweight Backstage build is infeasible in the environment, a documented fallback catalog-server (Go) serves the same Backstage-format entities.

**Tech Stack:** Python 3.12 (generator), Backstage (Node 20, built in-container), SQLite (better-sqlite3), kind, kubectl, Go 1.22 (fallback catalog-server only).

## Global Constraints

- Cluster `kind` named `streamflix`, context `kind-streamflix`. Every kubectl passes `--context kind-streamflix`. NEVER target `*-prod` EKS.
- Backstage runs in a new namespace `backstage`. Image `localhost:5001/streamflix-backstage:dev` (or `...-catalog-server:dev` for the fallback). All platform code under `platform/backstage/`.
- Catalog entity names use the SAME `_k8s_name` rule as the manifest generator: service short = id after colon; name = `<short>` if it already ends in `-service`, else `<short>-service`. So Component names match the running k8s services exactly.
- Entity counts from the graph: 1 System (`streamflix`), 13 Groups (one per `team:*`), 12 Users (one per `person:*`), 35 Components (one per `service:*`).
- Every Component MUST have an owner: from `OWNS_SERVICE` when present, else default `group:platform-engineering`.
- `dependsOn` from `DEPENDS_ON` edges as `component:<dep-name>`; `User.spec.memberOf` from `MEMBER_OF` edges (group short names); `Component.spec.owner` as `group:<team-short>`.
- Commit author `lakshminarayana-sys`, signed, no Claude trailer: `git -c user.name=lakshminarayana-sys commit -m "..."`. Repo root `/Users/lnv/Documents/maven`; stage only each task's files; never `git add -A`. Confirm branch is `main` before committing.
- Python: `source .venv/bin/activate`; run pytest from `projects/nexusgraph-ai`. Docker/kind available; node:20 base used for the in-container build (do not rely on host node/yarn).

---

### Task 1: Catalog generator + structural validation

**Files:**
- Create: `platform/backstage/generate_catalog.py`
- Create: `platform/backstage/test_generate_catalog.py`
- Create (generated, committed snapshot): `platform/backstage/catalog/catalog.yaml`

**Interfaces:**
- Produces: `load_nodes(path)->dict`, `load_edges(path)->list[tuple]`, `build_entities(nodes, edges)->list[dict]`, `validate(entities)->list[str]` (returns a list of problem strings; empty = valid), `render(entities)->str` (multi-doc YAML), `main(out, nodes, edges)`. CLI `python generate_catalog.py --out catalog/catalog.yaml`.
- `_k8s_name(short)` identical to the manifest generator's rule.

- [ ] **Step 1: Write the failing test `test_generate_catalog.py`**

```python
import textwrap
from pathlib import Path

from generate_catalog import load_nodes, load_edges, build_entities, validate, _k8s_name


def _root():
    return Path(__file__).resolve().parents[2]


def test_k8s_name_no_double_suffix():
    assert _k8s_name("playback") == "playback-service"
    assert _k8s_name("account-service") == "account-service"


def test_build_entities_counts_and_owner():
    root = _root()
    nodes = load_nodes(root / "graph" / "nodes.csv")
    edges = load_edges(root / "graph" / "edges.csv")
    ents = build_entities(nodes, edges)
    kinds = {}
    for e in ents:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    assert kinds.get("System") == 1
    assert kinds.get("Group") == 13
    assert kinds.get("User") == 12
    assert kinds.get("Component") == 35
    billing = next(e for e in ents if e["kind"] == "Component" and e["metadata"]["name"] == "billing-service")
    assert billing["spec"]["owner"] == "group:billing-platform"
    assert "component:payment-gateway-service" in billing["spec"]["dependsOn"]
    # an imported service with no OWNS_SERVICE edge defaults its owner
    acct = next(e for e in ents if e["kind"] == "Component" and e["metadata"]["name"] == "account-service")
    assert acct["spec"]["owner"] == "group:platform-engineering"


def test_validate_clean():
    root = _root()
    nodes = load_nodes(root / "graph" / "nodes.csv")
    edges = load_edges(root / "graph" / "edges.csv")
    problems = validate(build_entities(nodes, edges))
    assert problems == [], f"validation problems: {problems}"
```

- [ ] **Step 2: Run → fail**

Run: `cd platform/backstage && python -m pytest test_generate_catalog.py -v 2>&1 | head`
Expected: FAIL (`ModuleNotFoundError: generate_catalog`).

- [ ] **Step 3: Implement `generate_catalog.py`**

```python
"""Generate Backstage catalog entities from the StreamFlix graph CSVs."""
import argparse
import csv
import io
from pathlib import Path

import yaml

SYSTEM = "streamflix"
DEFAULT_OWNER = "platform-engineering"

# Known per-service failure mode → runbook slug (services that model a failure mode).
RUNBOOK_BY_SERVICE = {
    "playback-service": "cpu_throttle",
    "billing-service": "oom_kill",
    "identity-service": "image_pull_backoff",
    "recommendation-service": "memory_leak",
    "observability-service": "high_error_rate",
}


def _short(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def _k8s_name(short: str) -> str:
    return short if short.endswith("-service") else f"{short}-service"


def load_nodes(path: Path) -> dict:
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["id"]] = row
    return out


def load_edges(path: Path) -> list:
    out = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append((row["source"], row["relationship"], row["target"]))
    return out


def build_entities(nodes: dict, edges: list) -> list:
    services = {nid: n for nid, n in nodes.items() if n.get("label") == "Service"}
    teams = {nid: n for nid, n in nodes.items() if n.get("label") == "Team"}
    people = {nid: n for nid, n in nodes.items() if n.get("label") == "Person"}

    owner_of = {}      # service_id -> team_short
    depends = {}       # service_id -> [component names]
    member_of = {}     # person_id -> [group shorts]
    for src, rel, tgt in edges:
        rel_u = rel.upper()
        if rel_u == "OWNS_SERVICE":
            owner_of[tgt] = _short(src)
        elif rel_u == "DEPENDS_ON":
            depends.setdefault(src, []).append(f"component:{_k8s_name(_short(tgt))}")
        elif rel_u == "MEMBER_OF":
            member_of.setdefault(src, []).append(_short(tgt))

    entities = []
    entities.append({
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "System",
        "metadata": {"name": SYSTEM, "description": "StreamFlix streaming platform"},
        "spec": {"owner": f"group:{DEFAULT_OWNER}"},
    })
    for tid, t in teams.items():
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "metadata": {"name": _short(tid), "description": t.get("description", "")},
            "spec": {"type": "team", "profile": {"displayName": t.get("name", _short(tid))}, "children": []},
        })
    for pid, p in people.items():
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "User",
            "metadata": {"name": _short(pid), "description": p.get("description", "")},
            "spec": {"profile": {"displayName": p.get("name", _short(pid))}, "memberOf": member_of.get(pid, [])},
        })
    for sid, s in services.items():
        name = _k8s_name(_short(sid))
        owner = owner_of.get(sid, DEFAULT_OWNER)
        tier = (s.get("description") or "internal").strip()
        tag = "customer-facing" if tier == "customer-facing" else "internal"
        annotations = {
            "prometheus.io/service": name,
            "streamflix.io/grafana": f"http://localhost:3000/explore?query=rate(http_requests_total%7Bservice%3D%22{name}%22%7D%5B5m%5D)",
        }
        if name in RUNBOOK_BY_SERVICE:
            annotations["streamflix.io/runbook"] = f"platform/runbooks/{RUNBOOK_BY_SERVICE[name]}.md"
        spec = {
            "type": "service",
            "lifecycle": "production",
            "owner": f"group:{owner}",
            "system": SYSTEM,
        }
        deps = sorted(set(depends.get(sid, [])))
        if deps:
            spec["dependsOn"] = deps
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {"name": name, "description": f"StreamFlix {name}", "tags": [tag], "annotations": annotations},
            "spec": spec,
        })
    return entities


def validate(entities: list) -> list:
    problems = []
    comp_names = {e["metadata"]["name"] for e in entities if e["kind"] == "Component"}
    group_names = {e["metadata"]["name"] for e in entities if e["kind"] == "Group"}
    for e in entities:
        name = e["metadata"]["name"]
        if not name.islower() or " " in name:
            problems.append(f"{e['kind']} name not backstage-valid: {name}")
        if e["kind"] == "Component":
            owner = e["spec"].get("owner", "")
            if not owner.startswith("group:") or owner.split(":", 1)[1] not in group_names:
                problems.append(f"Component {name} owner missing/unknown: {owner}")
            for dep in e["spec"].get("dependsOn", []):
                target = dep.split(":", 1)[1]
                if target not in comp_names:
                    problems.append(f"Component {name} dependsOn unknown component: {target}")
        if e["kind"] == "User":
            for grp in e["spec"].get("memberOf", []):
                if grp not in group_names:
                    problems.append(f"User {name} memberOf unknown group: {grp}")
    return problems


def render(entities: list) -> str:
    buf = io.StringIO()
    yaml.safe_dump_all(entities, buf, sort_keys=False, default_flow_style=False)
    return buf.getvalue()


def main(out: str, nodes_path: str, edges_path: str) -> None:
    nodes = load_nodes(Path(nodes_path))
    edges = load_edges(Path(edges_path))
    entities = build_entities(nodes, edges)
    problems = validate(entities)
    if problems:
        raise SystemExit("catalog validation failed:\n" + "\n".join(problems))
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(entities))
    print(f"wrote {out} with {len(entities)} entities")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="catalog/catalog.yaml")
    ap.add_argument("--nodes", default="../../graph/nodes.csv")
    ap.add_argument("--edges", default="../../graph/edges.csv")
    a = ap.parse_args()
    main(a.out, a.nodes, a.edges)
```

- [ ] **Step 4: Run → pass**

Run: `cd platform/backstage && python -m pytest test_generate_catalog.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Generate the committed catalog snapshot**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai/platform/backstage
python generate_catalog.py --out catalog/catalog.yaml --nodes ../../graph/nodes.csv --edges ../../graph/edges.csv
grep -c "^kind: Component" catalog/catalog.yaml
```
Expected: prints `wrote catalog/catalog.yaml with 61 entities` (1+13+12+35) and the grep prints `35`.

- [ ] **Step 6: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/backstage/generate_catalog.py \
        projects/nexusgraph-ai/platform/backstage/test_generate_catalog.py \
        projects/nexusgraph-ai/platform/backstage/catalog/catalog.yaml
git -c user.name=lakshminarayana-sys commit -m "feat(platform): Backstage catalog generator from graph + validated snapshot"
```

---

### Task 2: Backstage app image (in-container build) — PRIMARY, with fallback contingency

**Files:**
- Create: `platform/backstage/app-config.yaml`
- Create: `platform/backstage/Dockerfile`
- (Contingency only) Create: `platform/backstage/catalog-server/{go.mod,main.go,main_test.go,Dockerfile}`

**Interfaces:**
- Produces image `localhost:5001/streamflix-backstage:dev` serving Backstage on `:7007` with the catalog loaded from `/catalog/catalog.yaml`; catalog API at `GET /api/catalog/entities`.
- Contingency image `localhost:5001/streamflix-catalog-server:dev` serving `GET /api/catalog/entities` (reads `/catalog/catalog.yaml`, returns the entities as JSON) + `GET /healthz` on `:7007`.

- [ ] **Step 1: Write `app-config.yaml`**

```yaml
app:
  title: StreamFlix Software Catalog
  baseUrl: http://localhost:7007
organization:
  name: StreamFlix
backend:
  baseUrl: http://localhost:7007
  listen:
    host: 0.0.0.0
    port: 7007
  cors:
    origin: http://localhost:7007
  database:
    client: better-sqlite3
    connection: ':memory:'
auth:
  providers:
    guest: {}
catalog:
  rules:
    - allow: [Component, System, Group, User, Resource, Location, Domain, API]
  locations:
    - type: file
      target: /catalog/catalog.yaml
```

- [ ] **Step 2: Write `Dockerfile`** (in-container scaffold + build; host node/yarn unused)

```dockerfile
# Stage 1: scaffold + build a Backstage backend on Node 20.
FROM node:20-bookworm AS build
WORKDIR /work
ENV CI=true
# Scaffold a Backstage app non-interactively (pinned). --path sets dir+name, --skip-install lets us control install.
RUN npx --yes @backstage/create-app@0.5.25 --path streamflix-backstage --skip-install
WORKDIR /work/streamflix-backstage
# Overlay our app-config (SQLite + guest + file catalog location).
COPY app-config.yaml ./app-config.production.yaml
RUN corepack enable && yarn install --network-timeout 600000
RUN yarn tsc && yarn build:backend --config app-config.yaml --config app-config.production.yaml

# Stage 2: runtime.
FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /work/streamflix-backstage/yarn.lock /work/streamflix-backstage/package.json ./
COPY --from=build /work/streamflix-backstage/packages/backend/dist/skeleton.tar.gz ./
RUN tar xzf skeleton.tar.gz && rm skeleton.tar.gz && corepack enable && yarn install --production --network-timeout 600000
COPY --from=build /work/streamflix-backstage/packages/backend/dist/bundle.tar.gz ./
RUN tar xzf bundle.tar.gz && rm bundle.tar.gz
COPY app-config.yaml ./app-config.yaml
EXPOSE 7007
CMD ["node", "packages/backend", "--config", "app-config.yaml"]
```

- [ ] **Step 3: Build the Backstage image (PRIMARY path)**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai/platform/backstage
docker build -t localhost:5001/streamflix-backstage:dev . 2>&1 | tail -30
```
Expected: image builds. The `create-app` + `yarn install` + build is large (several minutes, ~1.5GB download).

**If the build SUCCEEDS:** skip Step 4; go to Step 5 (commit the Backstage app files).

**If the build FAILS** (create-app flag mismatch, Node/yarn toolchain error, or it does not complete): do NOT spend more than two debugging attempts. Switch to the documented fallback (Step 4), and report this as a DONE_WITH_CONCERNS at task end, stating exactly what failed. The fallback yields a real, queryable catalog API serving the SAME generated entities.

- [ ] **Step 4: CONTINGENCY — fallback catalog-server (only if Step 3 failed)**

Create `platform/backstage/catalog-server/go.mod`:
```
module streamflix-catalog-server

go 1.22

require gopkg.in/yaml.v3 v3.0.1
```

Create `platform/backstage/catalog-server/main.go`:
```go
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"gopkg.in/yaml.v3"
)

func loadCatalog(path string) ([]map[string]any, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	dec := yaml.NewDecoder(f)
	var out []map[string]any
	for {
		var doc map[string]any
		if err := dec.Decode(&doc); err != nil {
			break
		}
		if doc != nil {
			out = append(out, doc)
		}
	}
	return out, nil
}

func main() {
	path := os.Getenv("CATALOG_PATH")
	if path == "" {
		path = "/catalog/catalog.yaml"
	}
	entities, err := loadCatalog(path)
	if err != nil {
		log.Printf("catalog load failed: %v", err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/catalog/entities", func(w http.ResponseWriter, r *http.Request) {
		kind := r.URL.Query().Get("filter")
		w.Header().Set("content-type", "application/json")
		if kind == "" {
			json.NewEncoder(w).Encode(entities)
			return
		}
		// filter=kind=component
		want := ""
		if len(kind) > 5 && kind[:5] == "kind=" {
			want = kind[5:]
		}
		var filtered []map[string]any
		for _, e := range entities {
			k, _ := e["kind"].(string)
			if want == "" || equalFold(k, want) {
				filtered = append(filtered, e)
			}
		}
		json.NewEncoder(w).Encode(filtered)
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("catalog-server serving %d entities on :7007", len(entities))
	log.Fatal(http.ListenAndServe(":7007", mux))
}

func equalFold(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := 0; i < len(a); i++ {
		ca, cb := a[i], b[i]
		if 'A' <= ca && ca <= 'Z' {
			ca += 32
		}
		if 'A' <= cb && cb <= 'Z' {
			cb += 32
		}
		if ca != cb {
			return false
		}
	}
	return true
}
```

Create `platform/backstage/catalog-server/main_test.go`:
```go
package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadCatalogMultiDoc(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "c.yaml")
	os.WriteFile(p, []byte("kind: System\nmetadata:\n  name: streamflix\n---\nkind: Component\nmetadata:\n  name: billing-service\n"), 0644)
	ents, err := loadCatalog(p)
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 2 {
		t.Fatalf("want 2 entities, got %d", len(ents))
	}
	if ents[1]["kind"] != "Component" {
		t.Fatalf("got %v", ents[1]["kind"])
	}
}
```

Create `platform/backstage/catalog-server/Dockerfile`:
```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 go build -o /catalog-server .
FROM gcr.io/distroless/static-debian12
COPY --from=build /catalog-server /catalog-server
EXPOSE 7007
ENTRYPOINT ["/catalog-server"]
```

Build + test the fallback:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai/platform/backstage/catalog-server
go test ./... && docker build -t localhost:5001/streamflix-catalog-server:dev .
```
Expected: test PASS, image builds.

- [ ] **Step 5: Commit (whichever path was taken)**

```bash
cd /Users/lnv/Documents/maven
# PRIMARY:
git add projects/nexusgraph-ai/platform/backstage/app-config.yaml projects/nexusgraph-ai/platform/backstage/Dockerfile
# plus, if the fallback was used:
#   git add projects/nexusgraph-ai/platform/backstage/catalog-server
git -c user.name=lakshminarayana-sys commit -m "feat(platform): Backstage app image (in-container build)"
# If fallback used, message: "feat(platform): Backstage app image + fallback catalog-server"
```
Report which path (PRIMARY Backstage or fallback catalog-server) was used and why.

---

### Task 3: Deploy + Makefile + live verify + README

**Files:**
- Create: `platform/backstage/k8s.yaml`
- Modify: `platform/Makefile` (add `backstage`, `backstage-up`, `backstage-verify`)
- Create: `platform/backstage/README.md`

**Interfaces:**
- Consumes: the catalog (Task 1), the image (Task 2 — Backstage or fallback).
- Produces: Backstage (or catalog-server) Deployment+Service in `backstage` ns; `make backstage` (generate catalog → ConfigMap → build+load → apply → rollout); `make backstage-up`; `make backstage-verify`.

- [ ] **Step 1: Write `k8s.yaml`** (uses the Backstage image; if the fallback was used in Task 2, change the image + container name to `streamflix-catalog-server` — same ports/mount)

```yaml
apiVersion: v1
kind: Namespace
metadata: {name: backstage}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: backstage, namespace: backstage, labels: {app: backstage}}
spec:
  replicas: 1
  selector: {matchLabels: {app: backstage}}
  template:
    metadata: {labels: {app: backstage}}
    spec:
      containers:
        - name: backstage
          image: localhost:5001/streamflix-backstage:dev
          ports: [{containerPort: 7007}]
          volumeMounts: [{name: catalog, mountPath: /catalog}]
          readinessProbe: {httpGet: {path: /healthz, port: 7007}, initialDelaySeconds: 10, periodSeconds: 5, failureThreshold: 30}
          resources:
            requests: {cpu: "250m", memory: "256Mi"}
            limits: {cpu: "1", memory: "1Gi"}
      volumes:
        - name: catalog
          configMap: {name: backstage-catalog}
---
apiVersion: v1
kind: Service
metadata: {name: backstage, namespace: backstage, labels: {app: backstage}}
spec: {selector: {app: backstage}, ports: [{port: 7007, targetPort: 7007}]}
```
Note: Backstage's health path is `/healthz` (the backend exposes it); the fallback catalog-server also serves `/healthz`. If the built Backstage uses a different health route, the implementer adjusts the probe path to one the backend serves (e.g. `/.backstage/health/v1/readiness`) and notes it.

- [ ] **Step 2: Add `backstage`, `backstage-up`, `backstage-verify` to `platform/Makefile`**

```makefile
.PHONY: backstage backstage-up backstage-verify
backstage:
	@python3 backstage/generate_catalog.py --out backstage/catalog/catalog.yaml --nodes ../graph/nodes.csv --edges ../graph/edges.csv
	@kubectl --context $(CTX) create namespace backstage --dry-run=client -o yaml | kubectl --context $(CTX) apply -f -
	@kubectl --context $(CTX) -n backstage create configmap backstage-catalog \
		--from-file=catalog.yaml=backstage/catalog/catalog.yaml \
		--dry-run=client -o yaml | kubectl --context $(CTX) apply -f -
	@docker build -t $(REG)/streamflix-backstage:dev backstage
	@docker push $(REG)/streamflix-backstage:dev
	@kind load docker-image $(REG)/streamflix-backstage:dev --name streamflix
	@kubectl --context $(CTX) apply -f backstage/k8s.yaml
	@kubectl --context $(CTX) -n backstage rollout status deploy/backstage --timeout=300s
	@echo "Backstage deployed in ns backstage."

backstage-up:
	@kubectl --context $(CTX) -n backstage port-forward svc/backstage 7007:7007 >/tmp/pf-backstage.log 2>&1 &
	@sleep 4
	@echo "Backstage at http://localhost:7007  (catalog API: http://localhost:7007/api/catalog/entities)"

backstage-verify:
	@kubectl --context $(CTX) -n backstage get pods -l app=backstage
	@echo "After backstage-up: curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=component' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)),\"components\")'"
```
(If the fallback image was used, change the three `streamflix-backstage` references in the `backstage` target to `streamflix-catalog-server` and the k8s.yaml image accordingly. Note this in the report.)

- [ ] **Step 3: Deploy for real**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai/platform
make backstage
kubectl --context kind-streamflix -n backstage get pods -l app=backstage
```
Expected: the backstage pod reaches Running/Ready. (Backstage's first boot can take 30-90s; the readiness probe has a generous failureThreshold.)

- [ ] **Step 4: ACCEPTANCE — catalog API returns the entities (run for real)**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai/platform
make backstage-up
sleep 3
echo "components:"; curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=component' | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d)); names=[e['metadata']['name'] for e in d]; print('billing-service' in names)"
echo "groups:"; curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=group' | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
echo "users:"; curl -s 'http://localhost:7007/api/catalog/entities?filter=kind=user' | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
```
Expected: components `35` and `True` (billing-service present); groups `13`; users `12`. Capture the output. (For the real Backstage, the catalog processor ingests the file location on boot; allow a few seconds and re-query if the first call returns fewer than 35 while it processes.)

- [ ] **Step 5: Write `platform/backstage/README.md`**

```markdown
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
Open http://localhost:7007 for the UI; the catalog API is at
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
```
(If the fallback catalog-server is in use, add one sentence: "This deployment serves the catalog API via a lightweight catalog-server; the full Backstage UI build was deferred — see the Phase 4 spec risk note.")

- [ ] **Step 6: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/backstage/k8s.yaml \
        projects/nexusgraph-ai/platform/Makefile \
        projects/nexusgraph-ai/platform/backstage/README.md
git -c user.name=lakshminarayana-sys commit -m "feat(platform): deploy Backstage catalog + make targets + README"
```

---

## Phase 4 Done = acceptance (spec §6)

1. Generator produces 1 System / 13 Groups / 12 Users / 35 Components; validation clean. (T1)
2. Backstage (or fallback) pod Running in ns `backstage`. (T3 Step 3)
3. `GET /api/catalog/entities?filter=kind=component` → 35, billing-service present with owner + dependsOn + annotations. (T3 Step 4)
4. groups → 13, users → 12. (T3 Step 4)
5. UI renders the catalog (real Backstage path) — best-effort; the catalog API is the guaranteed proof.

## Self-review notes

- **Coverage:** generator + validation + snapshot (T1), Backstage app image with fallback (T2), deploy + verify + README (T3). Spec §5 + §6 covered.
- **Name consistency:** `_k8s_name` identical to the manifest generator → Component names match running services; `dependsOn`/`owner`/`memberOf` reference resolved names; `validate()` enforces it.
- **Honesty flag (T2):** real Backstage in-container build is heavy and Node-version-sensitive (host Node 25, no yarn → built on node:20). If it's infeasible in the environment, the fallback catalog-server serves the SAME entities via the catalog API — a real, queryable catalog — and the implementer reports DONE_WITH_CONCERNS naming what failed. The catalog content (T1) is identical either way.
- **RUNBOOK_BY_SERVICE** maps the 5 services that model a failure mode to their runbook; other services simply omit the runbook annotation (not an error).
