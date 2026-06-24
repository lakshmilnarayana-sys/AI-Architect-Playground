#!/usr/bin/env bash
set -euo pipefail
reg_name='kind-registry'
reg_port='5001'
if [ "$(docker inspect -f '{{.State.Running}}' "${reg_name}" 2>/dev/null || true)" != 'true' ]; then
  docker run -d --restart=always -p "127.0.0.1:${reg_port}:5000" \
    --network bridge --name "${reg_name}" registry:2
fi
# Connect registry to the kind network (ignore error if already connected)
docker network connect "kind" "${reg_name}" 2>/dev/null || true
# Document the registry in-cluster (KEP-1755)
cat <<EOF | kubectl --context kind-streamflix apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${reg_port}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF
