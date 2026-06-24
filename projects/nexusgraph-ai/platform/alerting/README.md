# StreamFlix Alerting (Phase 2)

PrometheusRules fire on real cluster metrics, Alertmanager routes them to a local
alert-sink, and each alert links a runbook.

## Deploy

```bash
cd platform
make alerts          # build+load alert-sink, deploy it, apply rules, upgrade Alertmanager config
make alerts-verify   # show rule + sink status
```

## See alerts fire

```bash
make fault SVC=playback MODE=cpu_throttle VALUE=3 TTL=1200
kubectl --context kind-streamflix -n observability port-forward svc/alert-sink 18090:8080
curl localhost:18090/alerts | python3 -m json.tool     # firing StreamFlix alerts with runbook_url
make fault SVC=playback MODE=clear
```

## Alerts

StreamFlixHighErrorRate, StreamFlixHighLatencyP95, StreamFlixDownstreamFailures,
StreamFlixCPUThrottling, StreamFlixOOMKilled, StreamFlixPodCrashLooping,
StreamFlixImagePullBackOff, StreamFlixMemoryNearLimit. Each carries `severity` +
`failure_mode` (matching the incident agent's keys) and a `runbook_url` resolving to
`platform/runbooks/<slug>.md`.

## Routing

Alertmanager (kube-prometheus-stack) routes any `severity=SEV1|SEV2|SEV3` alert to the
`alert-sink` webhook (`http://alert-sink.observability.svc:8080/webhook`); SEV2 inhibits
SEV3 for the same service/pod. Phase 3 replaces the sink with the Slack mock.
