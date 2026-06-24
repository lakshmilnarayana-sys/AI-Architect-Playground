#!/usr/bin/env bash
set -euo pipefail
CTX=kind-streamflix
NS=observability
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null
helm repo update >/dev/null

helm --kube-context $CTX upgrade --install kps prometheus-community/kube-prometheus-stack \
  -n $NS --create-namespace -f observability/values/kube-prometheus-stack.yaml --wait --timeout 10m

helm --kube-context $CTX upgrade --install loki grafana/loki \
  -n $NS -f observability/values/loki.yaml --wait --timeout 10m

helm --kube-context $CTX upgrade --install promtail grafana/promtail \
  -n $NS --set "config.clients[0].url=http://loki-gateway/loki/api/v1/push" --wait --timeout 10m

helm --kube-context $CTX upgrade --install tempo grafana/tempo \
  -n $NS -f observability/values/tempo.yaml --wait --timeout 10m

echo "Observability installed."
