SHELL := /usr/bin/env bash
CTX := kind-streamflix
REG := localhost:5001

.PHONY: up down context observe build deploy verify fault alerts alerts-verify traces-verify incident-services incident-up incident-verify
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

fault:
	@bash scripts/inject_fault.sh $(SVC) $(MODE) $(VALUE) $(TTL)

alerts-verify:
	@echo "--- PrometheusRule ---"
	@kubectl --context $(CTX) -n observability get prometheusrule streamflix-alerts
	@echo "--- alert-sink pod ---"
	@kubectl --context $(CTX) -n observability get pods -l app=alert-sink
	@echo "--- recent alerts at the sink (port-forward then curl /alerts) ---"
	@echo "Run: kubectl --context $(CTX) -n observability port-forward svc/alert-sink 18090:8080  # then curl localhost:18090/alerts"

traces-verify:
	@echo "Port-forward Tempo then query a recent playback trace:"
	@echo "  kubectl --context $(CTX) -n observability port-forward svc/tempo 3200:3200"
	@echo "  curl -s 'http://localhost:3200/api/search?tags=service.name=playback-service&limit=1'"
	@echo "Then GET /api/traces/<traceID> and confirm multiple service.name values (fan-out)."

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
	@for d in slack-mock jira-mock oncall-registry; do \
		kubectl --context $(CTX) -n observability rollout status deploy/$$d --timeout=120s ; \
	done
	@helm --kube-context $(CTX) upgrade --install kps prometheus-community/kube-prometheus-stack \
		-n observability -f observability/values/kube-prometheus-stack.yaml --wait --timeout 10m
	@echo "Incident services deployed; Alertmanager → slack-mock."

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

alerts:
	@docker build -t $(REG)/streamflix-alert-sink:dev alerting/alert-sink
	@docker push $(REG)/streamflix-alert-sink:dev
	@kind load docker-image $(REG)/streamflix-alert-sink:dev --name streamflix
	@kubectl --context $(CTX) apply -f alerting/alert-sink/k8s.yaml
	@kubectl --context $(CTX) -n observability rollout status deploy/alert-sink --timeout=120s
	@kubectl --context $(CTX) apply -f alerting/rules/streamflix-alerts.yaml
	@helm --kube-context $(CTX) upgrade --install kps prometheus-community/kube-prometheus-stack \
		-n observability -f observability/values/kube-prometheus-stack.yaml --wait --timeout 10m
	@echo "Alerts deployed. Alertmanager routes SEV* to alert-sink."
