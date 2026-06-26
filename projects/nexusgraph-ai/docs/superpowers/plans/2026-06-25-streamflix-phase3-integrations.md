# StreamFlix Platform Phase 3 — Integrations + Live Incident Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the real incident loop — a firing Alertmanager alert drives the incident agent to run against live cluster + Prometheus signals, resolve on-call from a real registry, post to a Slack mock, and open a Jira mock ticket, all locally.

**Architecture:** Three tiny in-cluster Go mock services (slack-mock, jira-mock, oncall-registry) in `observability`, reached from the local Python agent via port-forward. The agent gets env-gated (`INCIDENT_LIVE`) "live providers" that read the real cluster/Prometheus and POST to the mocks, with the existing deterministic behavior as fallback. A local watcher polls Alertmanager and runs the pipeline on new StreamFlix alerts; a manual CLI does the same on demand.

**Tech Stack:** Go 1.22 (mocks, built in-container), Python 3.12 (agent providers, watcher, seed generator), kube-prometheus-stack/Alertmanager, kind, kubectl, Prometheus HTTP API, k8s API via kubectl.

## Global Constraints

- Cluster `kind` named `streamflix`, context `kind-streamflix`. Every kubectl/helm passes `--context kind-streamflix` / `--kube-context kind-streamflix`. NEVER target `*-prod` EKS.
- Mocks in namespace `observability`; images `localhost:5001/streamflix-slack-mock:dev`, `...-jira-mock:dev`, `...-oncall-registry:dev`. All platform code under `platform/`; agent code under `src/incident/`.
- **Additive + env-gated:** all live behavior behind `INCIDENT_LIVE=true`; with the flag unset, existing deterministic behavior and the eval suite are UNCHANGED. Live providers degrade to fallback on any error.
- Live provider dict shapes MUST match the existing ones: `kubernetes.py` runtime dict = output of `healthy_runtime`/`inject_failure` (keys: service, cluster, namespace, workload, active_failure, pod_status, health, restart_count_delta, signals); `observability.py` evidence items = `{kind, name, query}`.
- Endpoint env vars (localhost defaults for the local agent): `SLACK_MOCK_URL=http://localhost:18100`, `JIRA_MOCK_URL=http://localhost:18101`, `ONCALL_REGISTRY_URL=http://localhost:18102`, `PROMETHEUS_URL=http://localhost:9090`, `ALERTMANAGER_URL=http://localhost:9093`, `KUBE_CONTEXT=kind-streamflix`.
- Jira key scheme matches existing `jira.py._issue_key`: `INC-<sha1(incident_id)[:8] as int % 900000 + 100000>`.
- Commit author `lakshminarayana-sys`, signed, no Claude trailer: `git -c user.name=lakshminarayana-sys commit -m "..."`. Repo root `/Users/lnv/Documents/maven`; stage only each task's files; never `git add -A`.
- Python: `source .venv/bin/activate`; run pytest from repo `projects/nexusgraph-ai`. Go/docker from each service dir or `platform/`.

---

### Task 1: Three Go mock services

**Files:**
- Create: `platform/incident-services/slack-mock/{go.mod,store.go,store_test.go,main.go,Dockerfile}`
- Create: `platform/incident-services/jira-mock/{go.mod,key.go,key_test.go,main.go,Dockerfile}`
- Create: `platform/incident-services/oncall-registry/{go.mod,main.go,main_test.go,Dockerfile}`

**Interfaces:**
- Produces images `localhost:5001/streamflix-{slack-mock,jira-mock,oncall-registry}:dev`.
- slack-mock `:8080`: `POST /webhook` (Alertmanager), `POST /api/chat.postMessage` {channel,text,username}→{ok,ts,channel}, `GET /channels/{name}`, `GET /alerts`, `GET /healthz`.
- jira-mock `:8080`: `POST /rest/api/2/issue` {fields:{summary,...},incident_id?}→{key,id,self}, `GET /rest/api/2/issue/{key}`, `GET /issues`, `GET /healthz`.
- oncall-registry `:8080`: `GET /oncall/{service}`, `GET /escalation/{service}/{severity}`, `GET /schedules`, `GET /healthz`. Loads seed JSON from `/seed/oncall-seed.json` (env `SEED_PATH`, default that).
- jira-mock exports `issueKey(incidentID string) string` in key.go (Go port of `_issue_key`: `fmt.Sprintf("INC-%d", int(sha1[:8] as uint)%900000+100000)`).

- [ ] **Step 1: slack-mock — go.mod**

```
module streamflix-slack-mock

go 1.22
```

- [ ] **Step 2: slack-mock — failing test store_test.go**

```go
package main

import "testing"

func TestChannelStorePostAndGet(t *testing.T) {
	s := NewStore()
	s.PostMessage("#inc-billing", Message{Author: "bot", Text: "hello"})
	s.PostMessage("#inc-billing", Message{Author: "bot", Text: "world"})
	msgs := s.Channel("#inc-billing")
	if len(msgs) != 2 {
		t.Fatalf("want 2, got %d", len(msgs))
	}
	if msgs[0].Text != "world" {
		t.Fatalf("want newest-first, got %q", msgs[0].Text)
	}
	if msgs[0].Ts == "" {
		t.Fatal("expected a ts assigned")
	}
}
```

- [ ] **Step 3: Run → fail**

Run: `cd platform/incident-services/slack-mock && go test ./... 2>&1 | head`
Expected: FAIL `undefined: NewStore`.

- [ ] **Step 4: slack-mock — store.go**

```go
package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

type Message struct {
	Ts     string `json:"ts"`
	Author string `json:"author"`
	Text   string `json:"text"`
}

type Store struct {
	mu       sync.Mutex
	channels map[string][]Message
	alerts   []map[string]any
	seq      int64
}

func NewStore() *Store { return &Store{channels: map[string][]Message{}} }

func (s *Store) nextTs() string {
	n := atomic.AddInt64(&s.seq, 1)
	return fmt.Sprintf("%d.%06d", time.Now().Unix(), n)
}

func (s *Store) PostMessage(channel string, m Message) Message {
	s.mu.Lock()
	defer s.mu.Unlock()
	m.Ts = s.nextTs()
	s.channels[channel] = append(s.channels[channel], m)
	return m
}

func (s *Store) Channel(channel string) []Message {
	s.mu.Lock()
	defer s.mu.Unlock()
	src := s.channels[channel]
	out := make([]Message, len(src))
	for i, m := range src {
		out[len(src)-1-i] = m
	}
	return out
}

func (s *Store) AddAlert(a map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.alerts = append(s.alerts, a)
}

func (s *Store) Alerts() []map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]map[string]any, len(s.alerts))
	copy(out, s.alerts)
	return out
}
```

- [ ] **Step 5: Run → pass**

Run: `cd platform/incident-services/slack-mock && go test ./...`
Expected: PASS.

- [ ] **Step 6: slack-mock — main.go**

```go
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"
)

var store = NewStore()

func postMessage(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		Channel  string `json:"channel"`
		Text     string `json:"text"`
		Username string `json:"username"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if body.Channel == "" {
		body.Channel = "#incidents"
	}
	author := body.Username
	if author == "" {
		author = "incident-bot"
	}
	m := store.PostMessage(body.Channel, Message{Author: author, Text: body.Text})
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"ok": true, "ts": m.Ts, "channel": body.Channel})
}

func getChannel(w http.ResponseWriter, r *http.Request) {
	name := strings.TrimPrefix(r.URL.Path, "/channels/")
	if !strings.HasPrefix(name, "#") {
		name = "#" + name
	}
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.Channel(name))
}

func webhook(w http.ResponseWriter, r *http.Request) {
	var p struct {
		Alerts []map[string]any `json:"alerts"`
	}
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	for _, a := range p.Alerts {
		store.AddAlert(a)
		labels, _ := a["labels"].(map[string]any)
		log.Printf("alert received: %v", labels["alertname"])
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"ok":true}`))
}

func getAlerts(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.Alerts())
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/chat.postMessage", postMessage)
	mux.HandleFunc("/channels/", getChannel)
	mux.HandleFunc("/webhook", webhook)
	mux.HandleFunc("/alerts", getAlerts)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("slack-mock listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```

- [ ] **Step 7: slack-mock — Dockerfile**

```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 go build -o /app .
FROM gcr.io/distroless/static-debian12
COPY --from=build /app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

- [ ] **Step 8: jira-mock — go.mod + key.go + failing key_test.go**

`go.mod`:
```
module streamflix-jira-mock

go 1.22
```
`key_test.go`:
```go
package main

import "testing"

func TestIssueKeyDeterministic(t *testing.T) {
	a := issueKey("incident:billing-oom")
	b := issueKey("incident:billing-oom")
	if a != b {
		t.Fatalf("not deterministic: %s vs %s", a, b)
	}
	if len(a) < 5 || a[:4] != "INC-" {
		t.Fatalf("bad key format: %s", a)
	}
}
```

- [ ] **Step 9: Run → fail**, then write `key.go`:

Run: `cd platform/incident-services/jira-mock && go test ./... 2>&1 | head` → FAIL `undefined: issueKey`.

`key.go` (port of `jira.py._issue_key`):
```go
package main

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"strconv"
)

func issueKey(incidentID string) string {
	sum := sha1.Sum([]byte(incidentID))
	hexstr := hex.EncodeToString(sum[:])[:8]
	n, _ := strconv.ParseInt(hexstr, 16, 64)
	return fmt.Sprintf("INC-%d", n%900000+100000)
}
```

- [ ] **Step 10: Run → pass**

Run: `cd platform/incident-services/jira-mock && go test ./...` → PASS.

- [ ] **Step 11: jira-mock — main.go**

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
)

type issue struct {
	Key    string         `json:"key"`
	ID     string         `json:"id"`
	Self   string         `json:"self"`
	Fields map[string]any `json:"fields"`
}

var (
	mu     sync.Mutex
	issues = map[string]issue{}
	seq    int64
)

func createIssue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		IncidentID string         `json:"incident_id"`
		Fields     map[string]any `json:"fields"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	var key string
	if body.IncidentID != "" {
		key = issueKey(body.IncidentID)
	} else {
		key = fmt.Sprintf("INC-%d", atomic.AddInt64(&seq, 1)+100000)
	}
	id := fmt.Sprintf("%d", atomic.AddInt64(&seq, 1))
	it := issue{Key: key, ID: id, Self: "/rest/api/2/issue/" + key, Fields: body.Fields}
	mu.Lock()
	issues[key] = it
	mu.Unlock()
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(it)
}

func getIssue(w http.ResponseWriter, r *http.Request) {
	key := strings.TrimPrefix(r.URL.Path, "/rest/api/2/issue/")
	mu.Lock()
	it, ok := issues[key]
	mu.Unlock()
	if !ok {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(it)
}

func listIssues(w http.ResponseWriter, _ *http.Request) {
	mu.Lock()
	out := make([]issue, 0, len(issues))
	for _, it := range issues {
		out = append(out, it)
	}
	mu.Unlock()
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(out)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/rest/api/2/issue", createIssue)
	mux.HandleFunc("/rest/api/2/issue/", getIssue)
	mux.HandleFunc("/issues", listIssues)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("jira-mock listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```
Dockerfile: identical to slack-mock's (Step 7).

- [ ] **Step 12: oncall-registry — go.mod + main.go + failing main_test.go**

`go.mod`:
```
module streamflix-oncall-registry

go 1.22
```
`main_test.go`:
```go
package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadSeedAndLookup(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "seed.json")
	os.WriteFile(p, []byte(`{"oncall":{"billing-service":{"schedule":"Billing Primary","person":"Daniel Okafor","team":"Billing Platform"}},"escalation":{"billing-service|SEV2":{"policy":"Billing SEV2","steps":["oncall","manager"]}}}`), 0644)
	seed, err := loadSeed(p)
	if err != nil {
		t.Fatal(err)
	}
	if seed.Oncall["billing-service"].Person != "Daniel Okafor" {
		t.Fatalf("got %+v", seed.Oncall["billing-service"])
	}
	if seed.Escalation["billing-service|SEV2"].Policy != "Billing SEV2" {
		t.Fatalf("got %+v", seed.Escalation["billing-service|SEV2"])
	}
}
```

- [ ] **Step 13: Run → fail**, then write `main.go`:

Run: `cd platform/incident-services/oncall-registry && go test ./... 2>&1 | head` → FAIL `undefined: loadSeed`.

`main.go`:
```go
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
)

type OncallEntry struct {
	Schedule string `json:"schedule"`
	Person   string `json:"person"`
	Team     string `json:"team"`
}
type EscalationEntry struct {
	Policy string   `json:"policy"`
	Steps  []string `json:"steps"`
}
type Seed struct {
	Oncall     map[string]OncallEntry     `json:"oncall"`
	Escalation map[string]EscalationEntry `json:"escalation"`
}

var seed Seed

func loadSeed(path string) (Seed, error) {
	var s Seed
	b, err := os.ReadFile(path)
	if err != nil {
		return s, err
	}
	err = json.Unmarshal(b, &s)
	return s, err
}

func getOncall(w http.ResponseWriter, r *http.Request) {
	svc := strings.TrimPrefix(r.URL.Path, "/oncall/")
	e, ok := seed.Oncall[svc]
	w.Header().Set("content-type", "application/json")
	if !ok {
		json.NewEncoder(w).Encode(map[string]any{"service": svc, "schedule": nil, "person": nil, "team": nil})
		return
	}
	json.NewEncoder(w).Encode(map[string]any{"service": svc, "schedule": e.Schedule, "person": e.Person, "team": e.Team})
}

func getEscalation(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/escalation/"), "/")
	w.Header().Set("content-type", "application/json")
	if len(parts) < 2 {
		http.Error(w, "need /escalation/{service}/{severity}", http.StatusBadRequest)
		return
	}
	key := parts[0] + "|" + parts[1]
	e, ok := seed.Escalation[key]
	if !ok {
		json.NewEncoder(w).Encode(map[string]any{"service": parts[0], "severity": parts[1], "policy": nil, "steps": []string{}})
		return
	}
	json.NewEncoder(w).Encode(map[string]any{"service": parts[0], "severity": parts[1], "policy": e.Policy, "steps": e.Steps})
}

func getSchedules(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(seed.Oncall)
}

func main() {
	path := os.Getenv("SEED_PATH")
	if path == "" {
		path = "/seed/oncall-seed.json"
	}
	if s, err := loadSeed(path); err != nil {
		log.Printf("seed load failed (%v); serving empty", err)
	} else {
		seed = s
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/oncall/", getOncall)
	mux.HandleFunc("/escalation/", getEscalation)
	mux.HandleFunc("/schedules", getSchedules)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("oncall-registry listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
```
Dockerfile: identical to slack-mock's (Step 7).

- [ ] **Step 14: Run all three test suites + build all three images**

Run:
```bash
cd platform/incident-services
for d in slack-mock jira-mock oncall-registry; do (cd $d && go test ./...); done
for d in slack-mock jira-mock oncall-registry; do docker build -t localhost:5001/streamflix-$d:dev $d; done
```
Expected: 3 PASS, 3 images built.

- [ ] **Step 15: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/incident-services
git -c user.name=lakshminarayana-sys commit -m "feat(platform): slack/jira/oncall Go mock services for incident loop"
```

---

### Task 2: On-call seed generator + deploy + Alertmanager → slack-mock

**Files:**
- Create: `platform/incident-services/generate_oncall_seed.py`
- Create: `platform/incident-services/test_generate_oncall_seed.py`
- Create: `platform/incident-services/k8s.yaml` (3 Deployments + 3 Services + ConfigMap mount for oncall-registry)
- Modify: `platform/observability/values/kube-prometheus-stack.yaml` (receiver webhook URL → slack-mock)
- Modify: `platform/Makefile` (add `incident-services` target)

**Interfaces:**
- `generate_oncall_seed.py`: `build_seed(data_dir, graph_dir) -> dict` with keys `oncall` (service→{schedule,person,team}) and `escalation` (`<service>|<SEV>`→{policy,steps}); CLI `--out platform/incident-services/oncall-seed.json`.
- `make incident-services` generates the seed, creates/updates a ConfigMap from it, builds+`kind load`s the 3 images, applies k8s.yaml, helm-upgrades kps to point the alert receiver at slack-mock, rolls out.

- [ ] **Step 1: Failing test test_generate_oncall_seed.py**

```python
import json
from pathlib import Path
from generate_oncall_seed import build_seed

def test_build_seed_has_billing(tmp_path):
    # uses the real repo data/graph dirs
    root = Path(__file__).resolve().parents[2]
    seed = build_seed(root / "data", root / "graph")
    assert "oncall" in seed and "escalation" in seed
    # billing-service should resolve a team from OWNS_SERVICE (Billing Platform)
    assert "billing-service" in seed["oncall"]
    assert seed["oncall"]["billing-service"]["team"]
```

- [ ] **Step 2: Run → fail**

Run: `cd platform/incident-services && python -m pytest test_generate_oncall_seed.py -v 2>&1 | head`
Expected: FAIL (`ModuleNotFoundError: generate_oncall_seed`).

- [ ] **Step 3: Implement generate_oncall_seed.py**

```python
"""Build the on-call registry seed JSON from incident-agent ground-truth data."""
import argparse
import csv
import json
from pathlib import Path

import yaml

SEVERITIES = ["SEV1", "SEV2", "SEV3"]


def _load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open() as fh:
        return yaml.safe_load(fh) or []


def _service_short(service_id: str) -> str:
    return service_id.split(":", 1)[1] if ":" in service_id else service_id


def _team_by_service(graph_dir: Path) -> dict[str, str]:
    """service short name -> team display name, from OWNS_SERVICE edges."""
    nodes = {}
    npath, epath = graph_dir / "nodes.csv", graph_dir / "edges.csv"
    if npath.exists():
        with npath.open(newline="") as fh:
            for row in csv.DictReader(fh):
                nodes[row["id"]] = row.get("name", row["id"])
    out = {}
    if epath.exists():
        with epath.open(newline="") as fh:
            for e in csv.DictReader(fh):
                if "OWNS_SERVICE" in (e.get("relationship", "") or "").upper():
                    svc = _service_short(e["target"])
                    out[f"{svc}-service" if not svc.endswith("-service") else svc] = nodes.get(e["source"], e["source"])
    return out


def build_seed(data_dir: Path, graph_dir: Path) -> dict:
    teams = _team_by_service(graph_dir)
    schedules = _load_yaml(data_dir / "oncall_schedules.yaml")
    policies = _load_yaml(data_dir / "escalation_policies.yaml")

    oncall = {}
    for svc, team in teams.items():
        sched = None
        person = None
        token = svc.replace("-service", "")
        for s in schedules:
            blob = (str(s.get("name", "")) + " " + str(s.get("team", "")) + " " + str(s.get("service", ""))).lower()
            if token in blob or (team and team.lower() in blob):
                sched = s.get("name")
                person = s.get("primary") or s.get("oncall") or (s.get("rotation", [{}])[0].get("person") if s.get("rotation") else None)
                break
        oncall[svc] = {"schedule": sched or f"{team} On-Call", "person": person, "team": team}

    escalation = {}
    for svc in teams:
        token = svc.replace("-service", "")
        for sev in SEVERITIES:
            policy = None
            steps = []
            for p in policies:
                blob = (str(p.get("name", "")) + " " + str(p.get("description", ""))).lower()
                if token in blob and sev.lower() in blob:
                    policy = p.get("name")
                    steps = p.get("steps") or ["primary-oncall", "secondary-oncall", "engineering-manager"]
                    break
            if policy:
                escalation[f"{svc}|{sev}"] = {"policy": policy, "steps": steps}
    return {"oncall": oncall, "escalation": escalation}


def main(out: str, data_dir: str, graph_dir: str) -> None:
    seed = build_seed(Path(data_dir), Path(graph_dir))
    Path(out).write_text(json.dumps(seed, indent=2))
    print(f"wrote {out}: {len(seed['oncall'])} oncall, {len(seed['escalation'])} escalation")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="oncall-seed.json")
    ap.add_argument("--data", default="../../data")
    ap.add_argument("--graph", default="../../graph")
    a = ap.parse_args()
    main(a.out, a.data, a.graph)
```

- [ ] **Step 4: Run → pass**

Run: `cd platform/incident-services && python -m pytest test_generate_oncall_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Write k8s.yaml** (3 Deployments + Services in `observability`; oncall-registry mounts the seed ConfigMap at `/seed`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: slack-mock, namespace: observability, labels: {app: slack-mock}}
spec:
  replicas: 1
  selector: {matchLabels: {app: slack-mock}}
  template:
    metadata: {labels: {app: slack-mock}}
    spec:
      containers:
        - name: slack-mock
          image: localhost:5001/streamflix-slack-mock:dev
          ports: [{containerPort: 8080}]
          readinessProbe: {httpGet: {path: /healthz, port: 8080}, initialDelaySeconds: 2}
          resources: {requests: {cpu: 20m, memory: 16Mi}, limits: {cpu: 100m, memory: 64Mi}}
---
apiVersion: v1
kind: Service
metadata: {name: slack-mock, namespace: observability, labels: {app: slack-mock}}
spec: {selector: {app: slack-mock}, ports: [{port: 8080, targetPort: 8080}]}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: jira-mock, namespace: observability, labels: {app: jira-mock}}
spec:
  replicas: 1
  selector: {matchLabels: {app: jira-mock}}
  template:
    metadata: {labels: {app: jira-mock}}
    spec:
      containers:
        - name: jira-mock
          image: localhost:5001/streamflix-jira-mock:dev
          ports: [{containerPort: 8080}]
          readinessProbe: {httpGet: {path: /healthz, port: 8080}, initialDelaySeconds: 2}
          resources: {requests: {cpu: 20m, memory: 16Mi}, limits: {cpu: 100m, memory: 64Mi}}
---
apiVersion: v1
kind: Service
metadata: {name: jira-mock, namespace: observability, labels: {app: jira-mock}}
spec: {selector: {app: jira-mock}, ports: [{port: 8080, targetPort: 8080}]}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: oncall-registry, namespace: observability, labels: {app: oncall-registry}}
spec:
  replicas: 1
  selector: {matchLabels: {app: oncall-registry}}
  template:
    metadata: {labels: {app: oncall-registry}}
    spec:
      containers:
        - name: oncall-registry
          image: localhost:5001/streamflix-oncall-registry:dev
          ports: [{containerPort: 8080}]
          env: [{name: SEED_PATH, value: /seed/oncall-seed.json}]
          volumeMounts: [{name: seed, mountPath: /seed}]
          readinessProbe: {httpGet: {path: /healthz, port: 8080}, initialDelaySeconds: 2}
          resources: {requests: {cpu: 20m, memory: 16Mi}, limits: {cpu: 100m, memory: 64Mi}}
      volumes:
        - name: seed
          configMap: {name: oncall-seed}
---
apiVersion: v1
kind: Service
metadata: {name: oncall-registry, namespace: observability, labels: {app: oncall-registry}}
spec: {selector: {app: oncall-registry}, ports: [{port: 8080, targetPort: 8080}]}
```

- [ ] **Step 6: Point Alertmanager receiver at slack-mock**

In `platform/observability/values/kube-prometheus-stack.yaml`, change the `alert-sink` receiver webhook URL from `http://alert-sink.observability.svc:8080/webhook` to `http://slack-mock.observability.svc:8080/webhook`. Change ONLY that URL; leave route/matchers/inhibit intact.

- [ ] **Step 7: Add `incident-services` Makefile target**

```makefile
.PHONY: incident-services
incident-services:
	@python3 incident-services/generate_oncall_seed.py --out incident-services/oncall-seed.json --data ../data --graph ../graph
	@kubectl --context $(CTX) -n observability create configmap oncall-seed \
		--from-file=oncall-seed.json=incident-services/oncall-seed.json \
		--dry-run=client -o yaml | kubectl --context $(CTX) apply -f -
	@for d in slack-mock jira-mock oncall-registry; do \
		docker build -t $(REG)/streamflix-$$d:dev incident-services/$$d ; \
		docker push $(REG)/streamflix-$$d:dev ; \
		kind load docker-image $(REG)/streamflix-$$d:dev --name streamflix ; \
	done
	@kubectl --context $(CTX) apply -f incident-services/k8s.yaml
	@kubectl --context $(CTX) -n observability rollout restart deploy/oncall-registry
	@kubectl --context $(CTX) -n observability rollout status deploy/slack-mock --timeout=120s
	@helm --kube-context $(CTX) upgrade --install kps prometheus-community/kube-prometheus-stack \
		-n observability -f observability/values/kube-prometheus-stack.yaml --wait --timeout 10m
	@echo "Incident services deployed; Alertmanager → slack-mock."
```

- [ ] **Step 8: Run `make incident-services` and verify**

Run:
```bash
cd platform && make incident-services
kubectl --context kind-streamflix -n observability get pods -l 'app in (slack-mock,jira-mock,oncall-registry)'
kubectl --context kind-streamflix -n observability port-forward svc/oncall-registry 18102:8080 >/tmp/pf-oc.log 2>&1 &
sleep 4
curl -s localhost:18102/oncall/billing-service
kill %1 2>/dev/null
```
Expected: 3 pods Running; the curl returns billing-service with a non-null `team`.

- [ ] **Step 9: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/incident-services/generate_oncall_seed.py \
        projects/nexusgraph-ai/platform/incident-services/test_generate_oncall_seed.py \
        projects/nexusgraph-ai/platform/incident-services/k8s.yaml \
        projects/nexusgraph-ai/platform/observability/values/kube-prometheus-stack.yaml \
        projects/nexusgraph-ai/platform/Makefile
git -c user.name=lakshminarayana-sys commit -m "feat(platform): deploy incident mocks + oncall seed + Alertmanager to slack-mock"
```
(Do NOT commit the generated `oncall-seed.json` — add it to `platform/.gitignore` if not already ignored by `cluster/generated/`; explicitly `git rm --cached` is unnecessary since we don't add it.)

---

### Task 3: Agent live clients + Slack/Jira live posting (env-gated, with fallback)

**Files:**
- Create: `src/incident/live_clients.py`
- Create: `tests/test_live_clients.py`
- Modify: `src/incident/slack.py` (add `post_to_slack`)
- Modify: `src/incident/jira.py` (add `create_issue_live`)

**Interfaces:**
- `live_clients.py`: `live_enabled() -> bool` (True iff `INCIDENT_LIVE` truthy); `endpoint(name) -> str` (resolves the env vars w/ localhost defaults); `http_post_json(url, payload) -> dict|None` (returns parsed JSON, None on any error); `http_get_json(url) -> dict|list|None`.
- `slack.py`: `post_to_slack(channel: str, text: str, username: str = "incident-bot") -> dict|None` — when `live_enabled()`, POST slack-mock `/api/chat.postMessage`, return `{ok,ts,channel}`; else None.
- `jira.py`: `create_issue_live(state: dict) -> dict|None` — when `live_enabled()`, POST jira-mock `/rest/api/2/issue` with `incident_id` + `fields.summary` from `issue_from_state(state)`, return the created issue; else None (caller falls back to `save_incident`).

- [ ] **Step 1: Failing test tests/test_live_clients.py**

```python
import os
import src.incident.live_clients as lc


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    assert lc.live_enabled() is False


def test_live_enabled_truthy(monkeypatch):
    monkeypatch.setenv("INCIDENT_LIVE", "true")
    assert lc.live_enabled() is True


def test_endpoint_defaults(monkeypatch):
    monkeypatch.delenv("SLACK_MOCK_URL", raising=False)
    assert lc.endpoint("slack") == "http://localhost:18100"


def test_http_post_json_returns_none_on_error(monkeypatch):
    # unreachable port → None, never raises
    assert lc.http_post_json("http://localhost:1/none", {"a": 1}) is None
```

- [ ] **Step 2: Run → fail**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_live_clients.py -v 2>&1 | head`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement live_clients.py**

```python
"""Thin HTTP clients + env-gated live-mode toggle for the incident agent.

All live behavior is opt-in via INCIDENT_LIVE; every call returns None on any
error so callers fall back to deterministic behavior and never raise.
"""
from __future__ import annotations

import json
import os
import urllib.request

_DEFAULTS = {
    "slack": "http://localhost:18100",
    "jira": "http://localhost:18101",
    "oncall": "http://localhost:18102",
    "prometheus": "http://localhost:9090",
    "alertmanager": "http://localhost:9093",
}
_ENV = {
    "slack": "SLACK_MOCK_URL",
    "jira": "JIRA_MOCK_URL",
    "oncall": "ONCALL_REGISTRY_URL",
    "prometheus": "PROMETHEUS_URL",
    "alertmanager": "ALERTMANAGER_URL",
}


def live_enabled() -> bool:
    return str(os.getenv("INCIDENT_LIVE", "")).strip().lower() in ("1", "true", "yes", "on")


def endpoint(name: str) -> str:
    return os.getenv(_ENV[name], _DEFAULTS[name]).rstrip("/")


def http_post_json(url: str, payload: dict, timeout: float = 3.0):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else {}
    except Exception:
        return None


def http_get_json(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else None
    except Exception:
        return None
```

- [ ] **Step 4: Run → pass**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_live_clients.py -v`
Expected: PASS.

- [ ] **Step 5: Add `post_to_slack` to slack.py + `create_issue_live` to jira.py**

Append to `src/incident/slack.py`:
```python
def post_to_slack(channel: str, text: str, username: str = "incident-bot"):
    """Post to the live slack-mock when INCIDENT_LIVE; else return None (caller renders in-memory)."""
    from src.incident.live_clients import live_enabled, endpoint, http_post_json
    if not live_enabled():
        return None
    return http_post_json(
        f"{endpoint('slack')}/api/chat.postMessage",
        {"channel": channel, "text": text, "username": username},
    )
```

Append to `src/incident/jira.py`:
```python
def create_issue_live(state: dict):
    """Create an issue in the live jira-mock when INCIDENT_LIVE; else None (caller uses save_incident)."""
    from src.incident.live_clients import live_enabled, endpoint, http_post_json
    if not live_enabled():
        return None
    issue = issue_from_state(state)
    return http_post_json(
        f"{endpoint('jira')}/rest/api/2/issue",
        {"incident_id": issue.get("incident_id") or "incident", "fields": {"summary": issue.get("summary"), "severity": issue.get("severity"), "services": issue.get("services")}},
    )
```

- [ ] **Step 6: Test both new functions are no-ops when disabled**

Add to `tests/test_live_clients.py`:
```python
def test_post_to_slack_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.slack import post_to_slack
    assert post_to_slack("#inc", "hi") is None


def test_create_issue_live_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.jira import create_issue_live
    assert create_issue_live({"incident": {"id": "x"}}) is None
```
Run: `python -m pytest tests/test_live_clients.py -v` → PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/src/incident/live_clients.py \
        projects/nexusgraph-ai/tests/test_live_clients.py \
        projects/nexusgraph-ai/src/incident/slack.py \
        projects/nexusgraph-ai/src/incident/jira.py
git -c user.name=lakshminarayana-sys commit -m "feat(incident): env-gated live Slack/Jira clients with deterministic fallback"
```

---

### Task 4: Live cluster + Prometheus + on-call providers (env-gated, with fallback)

**Files:**
- Modify: `src/incident/kubernetes.py` (add `live_runtime`)
- Modify: `src/incident/observability.py` (add `live_evidence`)
- Modify: `src/incident/graph_lookup.py` (registry-first `oncall_for`/`escalation_for`)
- Create: `tests/test_live_providers.py`

**Interfaces:**
- `kubernetes.py`: `live_runtime(service: str) -> dict | None` — when `live_enabled()`, shell `kubectl --context $KUBE_CONTEXT -n streamflix-prod get pods -l app=<service> -o json` + events, map to the runtime dict shape (`active_failure` set from real OOMKilled/CrashLoopBackOff/ImagePullBackOff/restart delta); None on any error. `KUBE_CONTEXT` env (default `kind-streamflix`).
- `observability.py`: `live_evidence(service: str, failure_mode: str) -> list[dict] | None` — when `live_enabled()`, query Prometheus for the service's error ratio / p95 / throttle and return `{kind,name,query}` items; None on error.
- `graph_lookup.py`: `oncall_for`/`escalation_for` try the registry first when live, then existing fallback (signatures unchanged).

- [ ] **Step 1: Failing test tests/test_live_providers.py**

```python
def test_live_runtime_none_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.kubernetes import live_runtime
    assert live_runtime("billing-service") is None


def test_live_evidence_none_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.observability import live_evidence
    assert live_evidence("billing-service", "oom_kill") is None


def test_oncall_for_unchanged_when_disabled(monkeypatch):
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.graph_lookup import GraphContext
    ctx = GraphContext(use_neo4j=False)
    # deterministic fallback still resolves an owner-style dict or None, never raises
    res = ctx.oncall_for("billing-service")
    assert res is None or isinstance(res, dict)
```

- [ ] **Step 2: Run → fail**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_live_providers.py -v 2>&1 | head`
Expected: FAIL (`live_runtime`/`live_evidence` undefined).

- [ ] **Step 3: Add `live_runtime` to kubernetes.py**

```python
def live_runtime(service: str):
    """Read real pod status/events for a service; None if disabled or on any error."""
    import json as _json
    import os as _os
    import subprocess as _sp
    from src.incident.live_clients import live_enabled
    if not live_enabled():
        return None
    ctx = _os.getenv("KUBE_CONTEXT", "kind-streamflix")
    svc = normalize_service_name(service)
    try:
        out = _sp.run(
            ["kubectl", "--context", ctx, "-n", "streamflix-prod", "get", "pods",
             "-l", f"app={svc}", "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        pods = _json.loads(out.stdout).get("items", [])
        if not pods:
            return None
        restart_delta = 0
        active = None
        pod_status = "Running"
        for pod in pods:
            for cs in pod.get("status", {}).get("containerStatuses", []) or []:
                restart_delta = max(restart_delta, int(cs.get("restartCount", 0)))
                waiting = (cs.get("state", {}).get("waiting") or {}).get("reason")
                term = (cs.get("lastState", {}).get("terminated") or {}).get("reason")
                if term == "OOMKilled":
                    active, pod_status = "oom_kill", "OOMKilled"
                elif waiting in ("CrashLoopBackOff",):
                    active, pod_status = "pod_restart", "CrashLoopBackOff"
                elif waiting in ("ImagePullBackOff", "ErrImagePull"):
                    active, pod_status = "image_pull_backoff", "ImagePullBackOff"
        if active is None and restart_delta >= 3:
            active, pod_status = "pod_restart", "CrashLoopBackOff"
        return {
            "service": svc,
            "cluster": "streamflix",
            "namespace": "streamflix-prod",
            "workload": svc,
            "active_failure": active,
            "pod_status": pod_status,
            "health": "degraded" if active else "healthy",
            "restart_count_delta": restart_delta,
            "signals": {"source": "live-kubectl", "pods": len(pods)},
        }
    except Exception:
        return None
```

- [ ] **Step 4: Add `live_evidence` to observability.py**

```python
def live_evidence(service: str, failure_mode: str):
    """Query real Prometheus for the service's golden signals; None if disabled/error."""
    from src.incident.live_clients import live_enabled, endpoint, http_get_json
    if not live_enabled():
        return None
    import urllib.parse as _up
    base = endpoint("prometheus")
    queries = {
        "error_ratio": f'sum(rate(http_requests_total{{service="{service}",code=~"5.."}}[5m]))/sum(rate(http_requests_total{{service="{service}"}}[5m]))',
        "p95_latency": f'histogram_quantile(0.95,sum by (le)(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])))',
        "cpu_throttle": f'sum(rate(container_cpu_cfs_throttled_periods_total{{namespace="streamflix-prod"}}[5m]))/sum(rate(container_cpu_cfs_periods_total{{namespace="streamflix-prod"}}[5m]))',
    }
    items = []
    for name, q in queries.items():
        data = http_get_json(f"{base}/api/v1/query?query={_up.quote(q)}")
        value = None
        try:
            res = (data or {}).get("data", {}).get("result", [])
            if res:
                value = res[0]["value"][1]
        except Exception:
            value = None
        items.append({"kind": "metric", "name": f"live:{name}", "query": q, "value": value})
    items.append({"kind": "alert", "name": f"{failure_mode} detector (live)", "query": f"failure_mode={failure_mode}"})
    return items
```

- [ ] **Step 5: Registry-first oncall/escalation in graph_lookup.py**

In `src/incident/graph_lookup.py`, modify `oncall_for` and `escalation_for` to try the live registry first, then fall through to the existing logic. Replace the body of `oncall_for`:
```python
    def oncall_for(self, service: str) -> dict | None:
        live = self._registry_oncall(service)
        if live is not None:
            return live
        return self._edge_target(service, ("HAS_ONCALL_SCHEDULE", "ON_CALL"))
```
And `escalation_for` — add at the very top of the method body (before loading policies):
```python
        live = self._registry_escalation(service, severity)
        if live is not None:
            return live
```
Then add these helper methods to the class:
```python
    def _registry_oncall(self, service: str) -> dict | None:
        from src.incident.live_clients import live_enabled, endpoint, http_get_json
        if not live_enabled():
            return None
        data = http_get_json(f"{endpoint('oncall')}/oncall/{service}")
        if not data or not data.get("team"):
            return None
        return {"id": data.get("schedule"), "name": data.get("person") or data.get("schedule"), "team": data.get("team")}

    def _registry_escalation(self, service: str, severity: str) -> dict | None:
        from src.incident.live_clients import live_enabled, endpoint, http_get_json
        if not live_enabled():
            return None
        data = http_get_json(f"{endpoint('oncall')}/escalation/{service}/{severity}")
        if not data or not data.get("policy"):
            return None
        return {"id": data.get("policy"), "name": data.get("policy")}
```

- [ ] **Step 6: Run → pass + full eval-relevant suite stays green**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai
python -m pytest tests/test_live_providers.py tests/test_live_clients.py -v
python -m pytest tests/test_incident_eval.py -q
```
Expected: live-provider tests PASS; `test_incident_eval.py` still PASS (deterministic fallback unchanged with INCIDENT_LIVE unset).

- [ ] **Step 7: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/src/incident/kubernetes.py \
        projects/nexusgraph-ai/src/incident/observability.py \
        projects/nexusgraph-ai/src/incident/graph_lookup.py \
        projects/nexusgraph-ai/tests/test_live_providers.py
git -c user.name=lakshminarayana-sys commit -m "feat(incident): live kubectl/Prometheus/oncall providers with fallback"
```

---

### Task 5: Watcher + manual run CLI + wire live posting into the pipeline

**Files:**
- Create: `src/incident/run.py` (manual CLI + `seed_from_alert`)
- Create: `src/incident/watcher.py`
- Create: `tests/test_run_cli.py`
- Modify: `src/incident/declare.py` (call `post_to_slack` for the channel-open message when live) AND `src/incident/resolve.py` or wherever the Jira issue is saved (call `create_issue_live`, fall back to `save_incident`) — the implementer locates the existing `save_incident` call site.

**Interfaces:**
- `run.py`: `seed_from_alert(alert: dict) -> IncidentState` (maps an Alertmanager alert's `labels.alertname/service/severity/failure_mode` to a `new_incident` seed); `run_for_service(service, failure_mode=None, severity="SEV2") -> dict` (builds seed, calls `run_incident`, returns final state); `python -m src.incident.run --service <svc> [--failure-mode <m>] [--severity SEVn]`.
- `watcher.py`: `fetch_active_alerts() -> list[dict]` (GET Alertmanager `/api/v2/alerts?active=true` via endpoint); `watch(poll_seconds=15, once=False)` — dedupes by fingerprint, runs `run_for_service` on new StreamFlix alerts. `python -m src.incident.watcher`.

- [ ] **Step 1: Failing test tests/test_run_cli.py**

```python
def test_seed_from_alert_maps_labels():
    from src.incident.run import seed_from_alert
    alert = {"labels": {"alertname": "StreamFlixOOMKilled", "service": "billing-service",
                         "severity": "SEV2", "failure_mode": "oom_kill"}}
    state = seed_from_alert(alert)
    assert state["incident"]["affected_services"] == ["billing-service"]
    assert state["incident"]["severity"] == "SEV2"
    assert state["incident"]["failure_mode"] == "oom_kill"


def test_run_for_service_runs_pipeline(monkeypatch):
    # deterministic (INCIDENT_LIVE unset) — pipeline must complete and return timeline
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.run import run_for_service
    final = run_for_service("billing-service", failure_mode="oom_kill", severity="SEV2")
    assert "timeline" in final and len(final["timeline"]) > 0
```

- [ ] **Step 2: Run → fail**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_run_cli.py -v 2>&1 | head`
Expected: FAIL (`src.incident.run` missing).

- [ ] **Step 3: Implement run.py**

```python
"""Manual + programmatic entrypoint to run the incident pipeline for one service."""
from __future__ import annotations

import argparse

from src.incident.state import new_incident, IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident


def seed_from_alert(alert: dict) -> IncidentState:
    labels = alert.get("labels", {}) or {}
    service = labels.get("service") or labels.get("pod") or "unknown-service"
    severity = labels.get("severity", "SEV3")
    failure_mode = labels.get("failure_mode")
    alertname = labels.get("alertname", "StreamFlixAlert")
    state = new_incident(
        incident_id=f"incident:{alertname}:{service}",
        title=f"{alertname} on {service}",
        severity=severity,
        affected_services=[service],
        signal=(alert.get("annotations", {}) or {}).get("summary", alertname),
    )
    if failure_mode:
        state["incident"]["failure_mode"] = failure_mode
    state["incident"]["scenario_id"] = alertname
    return state


def run_for_service(service: str, failure_mode: str | None = None, severity: str = "SEV2") -> dict:
    state = new_incident(
        incident_id=f"incident:manual:{service}",
        title=f"Manual incident on {service}",
        severity=severity,
        affected_services=[service],
        signal=f"manual run for {service}",
    )
    if failure_mode:
        state["incident"]["failure_mode"] = failure_mode
    ctx = GraphContext(use_neo4j=False)
    return run_incident(state, ctx=ctx, use_vector=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", required=True)
    ap.add_argument("--failure-mode", default=None)
    ap.add_argument("--severity", default="SEV2")
    a = ap.parse_args()
    final = run_for_service(a.service, a.failure_mode, a.severity)
    print(f"incident complete: {len(final.get('timeline', []))} timeline events, "
          f"phase={final.get('phase')}")
    jira = (final.get("findings") or {}).get("jira_issue")
    if jira:
        print(f"jira: {jira.get('key')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run → pass**

Run: `cd /Users/lnv/Documents/maven/projects/nexusgraph-ai && python -m pytest tests/test_run_cli.py -v`
Expected: PASS (pipeline completes deterministically).

- [ ] **Step 5: Implement watcher.py**

```python
"""Poll Alertmanager for active StreamFlix alerts and run the incident pipeline."""
from __future__ import annotations

import time

from src.incident.live_clients import endpoint, http_get_json
from src.incident.run import seed_from_alert
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident

_SEEN: set[str] = set()


def fetch_active_alerts() -> list[dict]:
    data = http_get_json(f"{endpoint('alertmanager')}/api/v2/alerts?active=true")
    return data or []


def _is_streamflix(alert: dict) -> bool:
    return str((alert.get("labels", {}) or {}).get("alertname", "")).startswith("StreamFlix")


def process_once() -> int:
    ran = 0
    for alert in fetch_active_alerts():
        if not _is_streamflix(alert):
            continue
        fp = alert.get("fingerprint") or str(alert.get("labels"))
        if fp in _SEEN:
            continue
        _SEEN.add(fp)
        state = seed_from_alert(alert)
        run_incident(state, ctx=GraphContext(use_neo4j=False), use_vector=False)
        print(f"ran incident for {alert.get('labels', {}).get('alertname')} "
              f"/ {alert.get('labels', {}).get('service') or alert.get('labels', {}).get('pod')}")
        ran += 1
    return ran


def watch(poll_seconds: int = 15, once: bool = False) -> None:
    print(f"watcher polling Alertmanager every {poll_seconds}s (INCIDENT_LIVE recommended)")
    while True:
        try:
            process_once()
        except Exception as exc:  # never die on a transient error
            print(f"watch error: {type(exc).__name__}: {exc}")
        if once:
            return
        time.sleep(poll_seconds)


if __name__ == "__main__":
    watch()
```

- [ ] **Step 6: Wire live Slack/Jira into the pipeline (locate call sites)**

(a) Slack channel-open: in `src/incident/declare.py`, find where the incident channel/opening message is produced. After that message is created, add a best-effort live post:
```python
    from src.incident.slack import post_to_slack
    post_to_slack(channel_name(state["incident"]), f"Incident declared: {state['incident'].get('title','')}", username="incident-commander")
```
(import `channel_name` from `src.incident.slack` at the top if not present). This is best-effort: `post_to_slack` returns None when disabled and never raises.

(b) Jira: locate the existing `save_incident(state)` call (grep `save_incident(` under `src/incident/`). Wrap it so live mode posts to jira-mock and records the issue, falling back to the YAML store:
```python
    from src.incident.jira import create_issue_live, save_incident
    live_issue = create_issue_live(state)
    issue = live_issue or save_incident(state)
```
Store the resulting `issue` into `findings["jira_issue"]` the same way the surrounding code records findings (so `run.py` can print `jira['key']`). If `save_incident`'s result is already stored under a findings key, keep that and ALSO set `findings["jira_issue"] = issue`.

Note for the implementer: make these edits minimal and preserve existing deterministic behavior (with INCIDENT_LIVE unset, `create_issue_live` returns None and `post_to_slack` returns None, so the path is identical to today).

- [ ] **Step 7: Verify the deterministic suite is unaffected**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai
python -m pytest tests/test_run_cli.py tests/test_incident_eval.py -q
```
Expected: all PASS (the wiring is inert when INCIDENT_LIVE unset).

- [ ] **Step 8: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/src/incident/run.py \
        projects/nexusgraph-ai/src/incident/watcher.py \
        projects/nexusgraph-ai/tests/test_run_cli.py \
        projects/nexusgraph-ai/src/incident/declare.py \
        projects/nexusgraph-ai/src/incident/resolve.py
git -c user.name=lakshminarayana-sys commit -m "feat(incident): manual run CLI + Alertmanager watcher + live Slack/Jira wiring"
```
(Adjust the staged Jira-wiring file to whichever file actually contained `save_incident(` — the implementer commits exactly the files it edited.)

---

### Task 6: Live full-loop acceptance + Makefile incident-up/verify + README

**Files:**
- Modify: `platform/Makefile` (add `incident-up`, `incident-verify`)
- Create: `platform/incident-services/README.md`

**Interfaces:**
- `make incident-up` — start the port-forwards (slack-mock 18100, jira-mock 18101, oncall-registry 18102, Prometheus 9090, Alertmanager 9093) and print the env exports; `make incident-verify` — show the 3 pods + GET hints.

- [ ] **Step 1: Add `incident-up` + `incident-verify` to platform/Makefile**

```makefile
.PHONY: incident-up incident-verify
incident-up:
	@kubectl --context $(CTX) -n observability port-forward svc/slack-mock 18100:8080 >/tmp/pf-slack.log 2>&1 &
	@kubectl --context $(CTX) -n observability port-forward svc/jira-mock 18101:8080 >/tmp/pf-jira.log 2>&1 &
	@kubectl --context $(CTX) -n observability port-forward svc/oncall-registry 18102:8080 >/tmp/pf-oncall.log 2>&1 &
	@kubectl --context $(CTX) -n observability port-forward svc/kps-kube-prometheus-stack-prometheus 9090:9090 >/tmp/pf-prom.log 2>&1 &
	@kubectl --context $(CTX) -n observability port-forward svc/kps-kube-prometheus-stack-alertmanager 9093:9093 >/tmp/pf-am.log 2>&1 &
	@sleep 4
	@echo "Port-forwards up. Export these, then run the watcher or a manual run:"
	@echo "  export INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 ALERTMANAGER_URL=http://localhost:9093"
	@echo "  (cd .. && python -m src.incident.watcher)   # or: python -m src.incident.run --service billing-service --failure-mode oom_kill"

incident-verify:
	@kubectl --context $(CTX) -n observability get pods -l 'app in (slack-mock,jira-mock,oncall-registry)'
	@echo "GET endpoints (after make incident-up):"
	@echo "  curl localhost:18102/oncall/billing-service"
	@echo "  curl localhost:18100/alerts ; curl 'localhost:18100/channels/inc-...'"
	@echo "  curl localhost:18101/issues"
```

- [ ] **Step 2: ACCEPTANCE A — manual run posts to mocks (run for real)**

Run:
```bash
cd platform && make incident-services >/dev/null 2>&1 ; make incident-up
cd ..
export INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 ALERTMANAGER_URL=http://localhost:9093
python -m src.incident.run --service billing-service --failure-mode oom_kill --severity SEV2
echo "--- jira issues ---"; curl -s localhost:18101/issues | python3 -m json.tool | head -20
echo "--- oncall ---"; curl -s localhost:18102/oncall/billing-service
```
Expected: the run prints a timeline + a `jira: INC-xxxxxx`; `GET /issues` shows the created issue; `GET /oncall/billing-service` returns the schedule/person/team. Capture output.

- [ ] **Step 3: ACCEPTANCE B — full alert→watcher→agent loop (run for real)**

Run:
```bash
cd platform
# inject a real OOMKilled on billing (drives StreamFlixOOMKilled, Phase 2)
for i in $(seq 1 12); do bash scripts/inject_fault.sh billing oom_kill 1 300 >/dev/null 2>&1; sleep 2; done
cd ..
# run one watcher pass once the alert is firing (poll up to a few minutes)
for i in $(seq 1 10); do
  sleep 30
  python - <<'PY'
from src.incident.watcher import process_once
n = process_once()
print("ran", n)
PY
done
echo "--- slack-mock alerts ---"; curl -s localhost:18100/alerts | python3 -c "import sys,json; a=json.load(sys.stdin); print([x.get('labels',{}).get('alertname') for x in a])"
bash platform/scripts/inject_fault.sh billing clear >/dev/null 2>&1 || (cd platform && make fault SVC=billing MODE=clear)
```
Expected: slack-mock received `StreamFlixOOMKilled`, and at least one watcher pass reports `ran 1` (the agent ran for the alert). Capture the evidence. If the alert is slow, document the poll attempts; the manual run (Acceptance A) is the guaranteed proof, the loop is the bonus.

- [ ] **Step 4: ACCEPTANCE C — deterministic suite still green with flag unset**

Run:
```bash
cd /Users/lnv/Documents/maven/projects/nexusgraph-ai
unset INCIDENT_LIVE
python -m pytest tests/test_incident_eval.py tests/test_live_clients.py tests/test_live_providers.py tests/test_run_cli.py -q
```
Expected: all PASS — proves live mode is fully additive.

- [ ] **Step 5: Write platform/incident-services/README.md**

```markdown
# StreamFlix Incident Integrations (Phase 3)

Local mocks (slack/jira/oncall) + an env-gated live incident loop: a firing alert drives
the incident agent against the real cluster and posts to the mocks.

## Deploy
```bash
cd platform
make incident-services   # build+load mocks, seed on-call registry, point Alertmanager at slack-mock
make incident-up         # port-forwards + prints the env exports to use
make incident-verify
```

## Run the loop
```bash
export INCIDENT_LIVE=true SLACK_MOCK_URL=http://localhost:18100 JIRA_MOCK_URL=http://localhost:18101 \
  ONCALL_REGISTRY_URL=http://localhost:18102 PROMETHEUS_URL=http://localhost:9090 ALERTMANAGER_URL=http://localhost:9093
# manual:
python -m src.incident.run --service billing-service --failure-mode oom_kill
# automatic (polls Alertmanager):
python -m src.incident.watcher
```

## Verify
- `curl localhost:18102/oncall/billing-service` — on-call schedule/person/team (from graph data)
- `curl localhost:18101/issues` — Jira issues created by runs
- `curl localhost:18100/alerts` — alerts Alertmanager delivered; `curl 'localhost:18100/channels/inc-...'` — Slack thread

## Design
All live behavior is gated by `INCIDENT_LIVE`. Unset → the agent uses its deterministic
fallbacks and the eval suite is unchanged. The mocks replace the Phase-2 alert-sink as
Alertmanager's receiver. Phase 4 (Backstage) is separate.
```

- [ ] **Step 6: Commit**

```bash
cd /Users/lnv/Documents/maven
git add projects/nexusgraph-ai/platform/Makefile projects/nexusgraph-ai/platform/incident-services/README.md
git -c user.name=lakshminarayana-sys commit -m "feat(platform): incident-up/verify targets + Phase 3 README + live acceptance"
```

---

## Phase 3 Done = acceptance (spec §6)

1. 3 mock pods Running; oncall-registry returns billing's schedule/person/team. (T2 Step 8)
2. Alertmanager receiver is slack-mock; firing alert at slack-mock `/alerts`. (T6 Step 3)
3. Manual run end-to-end posts Slack thread + Jira issue + resolves on-call. (T6 Step 2)
4. Full loop: oom_kill → alert → watcher → agent run, verifiable via mocks. (T6 Step 3)
5. INCIDENT_LIVE unset → eval/tests still pass. (T6 Step 4)

## Self-review notes

- **Coverage:** mocks (T1), seed+deploy+AM routing (T2), live Slack/Jira clients (T3), live cluster/Prom/oncall providers (T4), watcher+CLI+pipeline wiring (T5), live acceptance+UX+README (T6). All spec §5 components + §6 acceptance covered.
- **Additivity:** every live path checks `live_enabled()` first and returns None/falls back; T4 Step 6 and T6 Step 4 explicitly assert the deterministic suite stays green with INCIDENT_LIVE unset.
- **Shape consistency:** `live_runtime` returns the exact `healthy_runtime`/`inject_failure` dict keys; `live_evidence` returns `{kind,name,query(,value)}`. Jira key scheme ported faithfully (`issueKey` Go == `_issue_key` Py). Endpoint env names + localhost ports consistent across live_clients.py, watcher.py, run.py, and the Makefile.
- **Honesty flag (T5 Step 6):** the exact file holding the `save_incident(` call must be located by grep; the implementer commits whichever file it edited (the plan names declare.py + resolve.py as the likely sites). The Jira/Slack wiring is inert when INCIDENT_LIVE is unset.
- **Honesty flag (T6 Step 3):** the full alert→watcher loop depends on the Phase-2 OOMKilled alert firing (1m `for`, proven in Phase 2); the manual run (Acceptance A) is the guaranteed proof if alert timing is slow in the moment.
