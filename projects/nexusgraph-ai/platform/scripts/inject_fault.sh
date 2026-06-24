#!/usr/bin/env bash
set -euo pipefail
CTX=kind-streamflix
SVC="${1:?service short name, e.g. playback}"
MODE="${2:?mode or 'clear'}"
VALUE="${3:-1}"
TTL="${4:-300}"
kubectl --context $CTX -n streamflix-prod port-forward "svc/${SVC}-service" 18080:8080 >/dev/null 2>&1 &
PF=$!
sleep 3
curl -s -X POST localhost:18080/admin/fault \
  -H 'content-type: application/json' \
  -d "{\"mode\":\"${MODE}\",\"value\":${VALUE},\"ttl\":${TTL}}"
echo
kill $PF 2>/dev/null || true
