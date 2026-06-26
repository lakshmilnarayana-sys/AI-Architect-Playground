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
