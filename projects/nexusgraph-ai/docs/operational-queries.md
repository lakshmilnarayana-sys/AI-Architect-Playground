# Operational Graph Queries

Use these in Neo4j Browser at http://localhost:7474.

## Service Operational Context

```cypher
MATCH (s:Service {name: 'playback-service'})
OPTIONAL MATCH (s)-[:HAS_ONCALL_SCHEDULE]->(schedule:OnCallSchedule)
OPTIONAL MATCH (schedule)-[:CURRENT_PRIMARY_ONCALL]->(primary:Person)
OPTIONAL MATCH (schedule)-[:CURRENT_SECONDARY_ONCALL]->(secondary:Person)
OPTIONAL MATCH (s)-[:HAS_DASHBOARD]->(dashboard:Dashboard)
OPTIONAL MATCH (s)-[:HAS_RUNBOOK]->(runbook:Runbook)
OPTIONAL MATCH (s)-[:HAS_SLO]->(slo:SLOMetric)
OPTIONAL MATCH (s)-[:USES_ESCALATION_POLICY]->(policy:EscalationPolicy)
RETURN s.name AS service,
       schedule.name AS oncall_schedule,
       primary.name AS current_primary_oncall,
       secondary.name AS current_secondary_oncall,
       collect(DISTINCT dashboard.name) AS dashboards,
       collect(DISTINCT runbook.name) AS runbooks,
       collect(DISTINCT slo.name) AS slo_metrics,
       collect(DISTINCT policy.name) AS escalation_policies;
```

## Current On-call By Service

```cypher
MATCH (service:Service)-[:HAS_ONCALL_SCHEDULE]->(schedule:OnCallSchedule)
OPTIONAL MATCH (schedule)-[:CURRENT_PRIMARY_ONCALL]->(primary:Person)
OPTIONAL MATCH (schedule)-[:CURRENT_SECONDARY_ONCALL]->(secondary:Person)
RETURN service.name AS service,
       schedule.name AS schedule,
       primary.name AS primary_oncall,
       secondary.name AS secondary_oncall
ORDER BY service;
```

## Incident Response Context

```cypher
MATCH (incident:Incident)-[:AFFECTED]->(service:Service)
OPTIONAL MATCH (incident)-[:USED_RUNBOOK]->(incident_runbook:Runbook)
OPTIONAL MATCH (incident)-[:OBSERVED_IN]->(dashboard:Dashboard)
OPTIONAL MATCH (incident)-[:TRIGGERED_ESCALATION_POLICY]->(policy:EscalationPolicy)
OPTIONAL MATCH (service)-[:HAS_ONCALL_SCHEDULE]->(schedule:OnCallSchedule)-[:CURRENT_PRIMARY_ONCALL]->(primary:Person)
RETURN incident.name AS incident,
       service.name AS affected_service,
       primary.name AS current_primary_oncall,
       collect(DISTINCT incident_runbook.name) AS incident_runbooks,
       collect(DISTINCT dashboard.name) AS dashboards,
       collect(DISTINCT policy.name) AS escalation_policies
ORDER BY incident, affected_service;
```

## Service Dependency With Datastores And Event Topics

```cypher
MATCH (service:Service {name: 'playback-service'})
OPTIONAL MATCH (service)-[:DEPENDS_ON]->(dependency:Service)
OPTIONAL MATCH (service)-[:USES_DATASTORE]->(datastore:Datastore)
OPTIONAL MATCH (service)-[:PUBLISHES_TO]->(published_topic:Topic)
OPTIONAL MATCH (service)-[:CONSUMES_FROM]->(consumed_topic:Topic)
RETURN service.name AS service,
       collect(DISTINCT dependency.name) AS dependencies,
       collect(DISTINCT datastore.name) AS datastores,
       collect(DISTINCT published_topic.name) AS publishes_to,
       collect(DISTINCT consumed_topic.name) AS consumes_from;
```

## Documentation References For A Service

```cypher
MATCH (service:Service {name: 'playback-service'})
OPTIONAL MATCH (service)-[:HAS_RUNBOOK]->(runbook:Runbook)
OPTIONAL MATCH (service)-[:HAS_ARCHITECTURE_DOC]->(architecture:ArchitectureDoc)
OPTIONAL MATCH (service)-[:HAS_OPENAPI_SPEC]->(openapi:OpenAPISpec)
OPTIONAL MATCH (service)-[:HAS_K8S_MANIFEST]->(manifest:KubernetesManifest)
RETURN service.name AS service,
       collect(DISTINCT runbook.name) AS runbooks,
       collect(DISTINCT architecture.name) AS architecture_docs,
       collect(DISTINCT openapi.name) AS openapi_specs,
       collect(DISTINCT manifest.name) AS k8s_manifests;
```
