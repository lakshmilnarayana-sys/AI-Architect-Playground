SHELL := /usr/bin/env bash
CTX := kind-streamflix
REG := localhost:5001

.PHONY: up down context observe build deploy verify
up:
	@command -v kind >/dev/null || { echo "kind not installed"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker not running"; exit 1; }
	@kind get clusters | grep -qx streamflix || kind create cluster --config cluster/kind-config.yaml
	@bash cluster/registry.sh
	@kubectl --context $(CTX) create namespace streamflix-prod --dry-run=client -o yaml | kubectl --context $(CTX) apply -f -
	@kubectl --context $(CTX) create namespace observability --dry-run=client -o yaml | kubectl --context $(CTX) apply -f -
	@echo "Cluster up. Context: $(CTX)"

down:
	@kind delete cluster --name streamflix || true
	@docker rm -f kind-registry 2>/dev/null || true

context:
	@kubectl config use-context $(CTX)

observe:
	@bash observability/install.sh

build:
	@docker build -t $(REG)/streamflix-service:dev services/streamflix-service
	@docker push $(REG)/streamflix-service:dev
	@docker build -t $(REG)/streamflix-loadgen:dev services/loadgen
	@docker push $(REG)/streamflix-loadgen:dev

deploy:
	@python3 scripts/generate_manifests.py --out cluster/generated --nodes ../graph/nodes.csv --edges ../graph/edges.csv
	@kubectl --context $(CTX) apply -f cluster/generated/
	@kubectl --context $(CTX) apply -f cluster/loadgen.yaml
	@kubectl --context $(CTX) apply -f cluster/servicemonitor.yaml
	@kubectl --context $(CTX) -n streamflix-prod rollout status deploy/playback-service --timeout=120s

verify:
	@kubectl --context $(CTX) get pods -n streamflix-prod
	@echo "--- Prometheus targets (port-forward then curl) ---"
	@echo "Run: kubectl --context $(CTX) -n observability port-forward svc/kps-grafana 3000:80  # admin/admin"
