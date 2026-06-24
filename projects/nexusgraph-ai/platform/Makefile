SHELL := /usr/bin/env bash
CTX := kind-streamflix
REG := localhost:5001

.PHONY: up down context observe
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
