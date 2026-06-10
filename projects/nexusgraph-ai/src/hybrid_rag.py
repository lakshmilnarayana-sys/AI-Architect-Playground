import os
import operator
import time
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_neo4j import Neo4jGraph
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Use relative imports if possible, or assume src is in path
try:
    from config import (
        DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD,
        LLM_PROVIDER, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL,
        DEFAULT_OLLAMA_MODEL
    )
    from vector_query import query_vector_store
except ImportError:
    from src.config import (
        DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD,
        LLM_PROVIDER, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL,
        DEFAULT_OLLAMA_MODEL
    )
    from src.vector_query import query_vector_store

# Load environment variables
load_dotenv()

class State(TypedDict):
    query: str
    route: Optional[str]
    context: Annotated[List[str], operator.add]
    answer: Optional[str]
    token_usage: Dict[str, int]
    trace: Optional[dict]


EMPTY_TOKEN_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def make_trace_stage(
    name: str,
    status: str,
    summary: str,
    elapsed: float | None = None,
    details: Optional[dict] = None,
) -> dict:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "elapsed": elapsed,
        "details": details or {},
    }


def empty_trace(mode: str) -> dict:
    return {
        "mode": mode,
        "stages": [],
        "evidence": {
            "vector": [],
            "graph": [],
            "merged": [],
        },
        "known_gaps": [],
    }


def merge_traces(mode: str, *traces: Optional[dict]) -> dict:
    merged = empty_trace(mode)
    for trace in traces:
        if not trace:
            continue
        merged["stages"].extend(trace.get("stages", []))
        evidence = trace.get("evidence", {})
        merged["evidence"]["vector"].extend(evidence.get("vector", []))
        merged["evidence"]["graph"].extend(evidence.get("graph", []))
        merged["evidence"]["merged"].extend(evidence.get("merged", []))
        merged["known_gaps"].extend(trace.get("known_gaps", []))
    if mode == "hybrid":
        merged["evidence"]["merged"].append({
            "summary": (
                f"Combined {len(merged['evidence']['vector'])} vector evidence items "
                f"and {len(merged['evidence']['graph'])} graph evidence items."
            )
        })
    return merged


def structured_payload(query: str, route: str, answer: str, trace: Optional[dict], token_usage: Optional[dict]) -> dict:
    trace = trace or empty_trace(route)
    return {
        "query": query,
        "route": route,
        "answer": answer,
        "token_usage": token_usage or EMPTY_TOKEN_USAGE,
        "evidence": trace.get("evidence", {}),
        "known_gaps": trace.get("known_gaps", []),
        "stages": trace.get("stages", []),
    }


def add_token_usage(current: Optional[dict], new_usage: Optional[dict]) -> dict:
    """Combine normalized token usage dictionaries."""
    current = current or EMPTY_TOKEN_USAGE
    new_usage = new_usage or EMPTY_TOKEN_USAGE
    return {
        "input_tokens": int(current.get("input_tokens", 0)) + int(new_usage.get("input_tokens", 0)),
        "output_tokens": int(current.get("output_tokens", 0)) + int(new_usage.get("output_tokens", 0)),
        "total_tokens": int(current.get("total_tokens", 0)) + int(new_usage.get("total_tokens", 0)),
    }


def extract_token_usage(response: Any) -> dict:
    """Normalize token usage metadata across LangChain chat providers."""
    usage = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}

    input_tokens = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or token_usage.get("input_tokens")
        or token_usage.get("prompt_tokens")
        or 0
    )
    output_tokens = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or token_usage.get("output_tokens")
        or token_usage.get("completion_tokens")
        or 0
    )
    total_tokens = (
        usage.get("total_tokens")
        or token_usage.get("total_tokens")
        or int(input_tokens) + int(output_tokens)
    )

    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
    }

# LLM for routing and synthesis
provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()

if provider == "gemini":
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", DEFAULT_GEMINI_MODEL),
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
elif provider == "groq":
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
        temperature=0
    )
elif provider == "ollama":
    llm = ChatOllama(
        model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0
    )
else: # default to openai
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        temperature=0
    )

graph: Neo4jGraph | None = None


def get_graph() -> Neo4jGraph:
    global graph
    if graph is None:
        graph = Neo4jGraph(
            url=os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI),
            username=os.getenv("NEO4J_USERNAME", DEFAULT_NEO4J_USERNAME),
            password=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
        )
    return graph

import re

# Cypher generation prompt with extremely rigid schema for small models
CYPHER_GENERATION_TEMPLATE = """Task: Generate a Cypher statement to query a Neo4j graph database.

Rules:
1. ONLY return the Cypher query. NO preamble.
2. DO NOT use curly braces {{}} for property filtering.
3. ALWAYS use the WHERE clause with the =~ operator for name searches.
4. Correct Pattern: MATCH (p:Person) WHERE p.name =~ '(?i)Emma Chen' ...

Schema:
{schema}

Example:
Question: How is Emma Chen related to the playback service?
Cypher: MATCH path=(p:Person)-[*1..3]-(s:Service) WHERE p.name =~ '(?i)Emma Chen' AND s.name =~ '(?i)playback.*' RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS nodes, [r IN relationships(path) | type(r)] AS relationships LIMIT 10

The question is:
{question}"""

WRITE_KEYWORDS = (
    'CREATE', 'MERGE', 'DELETE', 'DETACH', 'SET', 'REMOVE', 'DROP', 'LOAD CSV'
)

def is_read_only(cypher: str) -> bool:
    """Reject Cypher containing write/destructive clauses before execution."""
    upper = cypher.upper()
    return not any(keyword in upper for keyword in WRITE_KEYWORDS)

def clean_cypher(text: str) -> str:
    """Strip preamble, postamble, and markdown from Cypher string."""
    # Remove markdown backticks
    text = text.replace('```cypher', '').replace('```', '')
    
    # Find the actual MATCH or RETURN part
    match = re.search(r'(MATCH|RETURN|WITH)\s+.*', text, re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(0)
    
    # Remove everything after the last semicolon or RETURN statement
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if any(keyword in line.upper() for keyword in ['MATCH', 'WHERE', 'RETURN', 'WITH', 'UNWIND', 'LIMIT', 'SKIP', 'ORDER BY']):
            cleaned_lines.append(line)
        elif not cleaned_lines: continue
        else: break
            
    return '\n'.join(cleaned_lines).strip()

# Matches inline property-map filters like {name: "Emma Chen"} on a node pattern
PROPERTY_FILTER_PATTERN = re.compile(
    r'\((\w+)(:\w+)?\s*\{\s*(\w+)\s*:\s*[\'"]([^\'"]+)[\'"]\s*\}\)'
)

def rewrite_property_filters(cypher: str) -> str:
    """Rewrite inline `{prop: "value"}` exact-match filters into WHERE ... =~ clauses.

    Small local models routinely ignore the "no curly braces" rule and emit
    `(p:Person {name: "(?i)Emma Chen"})`, which Neo4j treats as an exact-equality
    map and matches nothing. Rewriting it deterministically into
    `(p:Person) WHERE p.name =~ '(?i)Emma Chen'` makes the query actually work
    regardless of whether the model follows the prompt's syntax rules.
    """
    conditions = []

    def replace(m):
        alias, label, prop, value = m.group(1), m.group(2) or '', m.group(3), m.group(4)
        clean_value = re.sub(r'^\(\?i\)', '', value)
        conditions.append(f"{alias}.{prop} =~ '(?i){clean_value}'")
        return f"({alias}{label})"

    rewritten = PROPERTY_FILTER_PATTERN.sub(replace, cypher)
    if not conditions:
        return cypher

    where_clause = ' AND '.join(conditions)
    if re.search(r'\bWHERE\b', rewritten, re.IGNORECASE):
        rewritten = re.sub(r'\bWHERE\b', f'WHERE {where_clause} AND', rewritten, count=1, flags=re.IGNORECASE)
    else:
        clause_match = re.search(r'\b(RETURN|WITH|ORDER BY|LIMIT|SKIP)\b', rewritten, re.IGNORECASE)
        if clause_match:
            idx = clause_match.start()
            rewritten = f"{rewritten[:idx]}WHERE {where_clause} {rewritten[idx:]}"
        else:
            rewritten = f"{rewritten} WHERE {where_clause}"

    return rewritten


def deterministic_cypher_for_query(query: str) -> Optional[str]:
    """Stable graph templates for demo queries where schema terms are known."""
    q = query.lower()

    if "observability unification plan" in q:
        return """
        MATCH (p {id: 'project:observability-unification'})-[:PRODUCED_DOCUMENT]->(d {id: 'document:observability-plan'})
        OPTIONAL MATCH (person:Person)-[:WORKED_ON]->(p)
        OPTIONAL MATCH (p)-[:USES_TOOL]->(tool)
        OPTIONAL MATCH (p)-[:MADE_DECISION]->(decision)
        OPTIONAL MATCH (p)-[:PRODUCED_OPERATIONAL_ARTIFACT]->(artifact)
        RETURN p.name AS project, p.description AS project_description,
               d.name AS document, d.description AS document_description,
               collect(DISTINCT person.name) AS contributors,
               collect(DISTINCT tool.name) AS tools,
               collect(DISTINCT decision.name) AS decisions,
               collect(DISTINCT artifact.name) AS operational_artifacts
        """
    if "playback resiliency rfc" in q:
        return """
        MATCH (p {id: 'project:playback-resiliency-2026'})-[:PRODUCED_DOCUMENT]->(d {id: 'document:playback-resiliency-rfc'})
        OPTIONAL MATCH (person:Person)-[:WORKED_ON]->(p)
        OPTIONAL MATCH (p)-[:USES_TOOL]->(tool)
        OPTIONAL MATCH (d)-[:RELATED_TO]->(decision)
        RETURN p.name AS project, p.description AS project_description,
               d.name AS document, d.description AS document_description,
               collect(DISTINCT person.name) AS contributors,
               collect(DISTINCT tool.name) AS tools,
               collect(DISTINCT decision.name) AS related_decisions
        """
    if "soc2 evidence pack" in q or "soc2 audit" in q:
        return """
        MATCH (p {id: 'project:soc2-readiness-audit'})-[:PRODUCED_DOCUMENT]->(d {id: 'document:soc2-evidence-pack'})
        OPTIONAL MATCH (person:Person)-[:WORKED_ON]->(p)
        OPTIONAL MATCH (p)-[:USES_TOOL]->(tool)
        OPTIONAL MATCH (d)-[:PART_OF_AUDIT]->(audit)
        RETURN p.name AS project, p.description AS project_description,
               d.name AS document, d.description AS document_description,
               audit.name AS audit,
               collect(DISTINCT person.name) AS contributors,
               collect(DISTINCT tool.name) AS tools
        """
    if "billing platform runbook" in q:
        return """
        MATCH (d {id: 'document:billing-platform-runbook'})
        OPTIONAL MATCH (d)-[:RELATED_TO]->(decision)
        OPTIONAL MATCH (d)-[:PART_OF_AUDIT]->(audit)
        OPTIONAL MATCH (team {id: 'team:billing-platform'})-[:OWNS_SERVICE]->(service)
        RETURN d.name AS document, d.description AS document_description,
               collect(DISTINCT decision.name) AS related_decisions,
               collect(DISTINCT audit.name) AS audits,
               team.name AS owner_team,
               collect(DISTINCT service.name) AS owned_services
        """
    service_runbook_ids = {
        "billing": "service:billing",
        "playback": "service:playback",
        "identity": "service:identity",
        "recommendation": "service:recommendation",
        "observability": "service:observability",
    }
    if "runbook" in q and "cover" in q:
        for service_name, service_id in service_runbook_ids.items():
            if service_name in q:
                return f"""
                MATCH (service {{id: '{service_id}'}})-[:HAS_RUNBOOK]->(runbook)
                OPTIONAL MATCH (service)-[:HAS_DASHBOARD]->(dashboard)
                OPTIONAL MATCH (service)-[:HAS_SLO]->(slo)
                OPTIONAL MATCH (service)-[:HAS_ONCALL_SCHEDULE]->(schedule)
                RETURN service.name AS service,
                       collect(DISTINCT runbook.name) AS runbooks,
                       collect(DISTINCT runbook.description) AS runbook_descriptions,
                       collect(DISTINCT dashboard.name) AS dashboards,
                       collect(DISTINCT slo.name) AS slos,
                       collect(DISTINCT schedule.name) AS schedules
                """
    if "customer identity threat model" in q:
        return """
        MATCH (d {id: 'document:identity-threat-model'})
        OPTIONAL MATCH (d)-[:RELATED_TO]->(decision)
        OPTIONAL MATCH (p {id: 'project:customer-identity-hardening'})
        OPTIONAL MATCH (person:Person)-[:WORKED_ON]->(p)
        RETURN d.name AS document, d.description AS document_description,
               p.name AS project, p.description AS project_description,
               collect(DISTINCT decision.name) AS related_decisions,
               collect(DISTINCT person.name) AS contributors
        """
    if "emma chen" in q and "playback" in q:
        return """
        MATCH path=(p:Person)-[*1..3]-(s:Service)
        WHERE p.name =~ '(?i)Emma Chen' AND s.name =~ '(?i)playback.*'
        RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS nodes,
               [r IN relationships(path) | type(r)] AS relationships
        LIMIT 10
        """
    if "worked on playback resiliency" in q and "kubernetes" in q:
        return """
        MATCH (person:Person)-[:WORKED_ON]->(project {id: 'project:playback-resiliency-2026'})
        MATCH (person)-[:HAS_SKILL]->(skill {id: 'skill:kubernetes'})
        RETURN person.name AS person, project.name AS project, skill.name AS skill
        """
    if "security governance team" in q and "tools" in q:
        return """
        MATCH (team {id: 'team:security-governance'})<-[:MEMBER_OF]-(person:Person)
        OPTIONAL MATCH (person)-[:WORKED_ON]->(project)-[:USES_TOOL]->(tool)
        RETURN team.name AS team,
               collect(DISTINCT person.name) AS people,
               collect(DISTINCT project.name) AS projects,
               collect(DISTINCT tool.name) AS tools
        """
    if ("oncall" in q or "on-call" in q) and ("today" in q or "schedule" in q) and "playback" not in q:
        return """
        MATCH (service:Service)
        OPTIONAL MATCH (service)-[:HAS_ONCALL_SCHEDULE]->(schedule)
        OPTIONAL MATCH (schedule)-[:CURRENT_PRIMARY_ONCALL]->(primary)
        OPTIONAL MATCH (schedule)-[:CURRENT_SECONDARY_ONCALL]->(secondary)
        OPTIONAL MATCH (team)-[:OWNS_SERVICE]->(service)
        OPTIONAL MATCH (service)-[:OWNED_BY_EXTERNAL_TEAM]->(external_team)
        RETURN service.name AS service,
               coalesce(schedule.name, 'No direct service on-call schedule modeled') AS schedule,
               coalesce(primary.name, 'Escalate to owner team') AS primary_oncall,
               coalesce(secondary.name, 'Escalate to owner team') AS secondary_oncall,
               coalesce(team.name, external_team.name, 'No owner modeled') AS owner_team
        ORDER BY service.name
        """
    service_names = extract_service_names_from_oncall_query(query)
    if service_names:
        service_list = ", ".join(f"'{name}'" for name in service_names)
        return f"""
        MATCH (service:Service)
        WHERE toLower(service.name) IN [{service_list}]
        OPTIONAL MATCH (service)-[:HAS_ONCALL_SCHEDULE]->(schedule)
        OPTIONAL MATCH (schedule)-[:CURRENT_PRIMARY_ONCALL]->(primary)
        OPTIONAL MATCH (schedule)-[:CURRENT_SECONDARY_ONCALL]->(secondary)
        OPTIONAL MATCH (team)-[:OWNS_SERVICE]->(service)
        OPTIONAL MATCH (service)-[:OWNED_BY_EXTERNAL_TEAM]->(external_team)
        RETURN service.name AS service,
               coalesce(schedule.name, 'No direct service on-call schedule modeled') AS schedule,
               coalesce(primary.name, 'Escalate to owner team') AS primary_oncall,
               coalesce(secondary.name, 'Escalate to owner team') AS secondary_oncall,
               coalesce(team.name, external_team.name, 'No owner modeled') AS owner_team
        ORDER BY service.name
        """
    dashboard_service_names = extract_service_names_from_dashboard_query(query)
    if dashboard_service_names:
        service_list = ", ".join(f"'{name}'" for name in dashboard_service_names)
        return f"""
        MATCH (service:Service)
        WHERE toLower(service.name) IN [{service_list}]
        OPTIONAL MATCH (service)-[:HAS_DASHBOARD]->(dashboard:Dashboard)
        OPTIONAL MATCH (team)-[:OWNS_SERVICE]->(service)
        OPTIONAL MATCH (service)-[:OWNED_BY_EXTERNAL_TEAM]->(external_team)
        RETURN service.name AS service,
               coalesce(dashboard.name, 'No dashboard coverage modeled') AS dashboard,
               coalesce(dashboard.description, 'No dashboard description modeled') AS dashboard_description,
               coalesce(team.name, external_team.name, 'No owner modeled') AS owner_team
        ORDER BY service.name
        """
    if "missing dashboard" in q or "without dashboard" in q or "dashboard coverage" in q and "missing" in q:
        return """
        MATCH (service:Service)
        WHERE NOT (service)-[:HAS_DASHBOARD]->(:Dashboard)
        OPTIONAL MATCH (team)-[:OWNS_SERVICE]->(service)
        OPTIONAL MATCH (service)-[:OWNED_BY_EXTERNAL_TEAM]->(external_team)
        RETURN service.name AS service,
               coalesce(team.name, external_team.name, 'No owner modeled') AS owner_team,
               service.description AS description
        ORDER BY service.name
        """
    if "services are owned" in q and "soc2" in q:
        return """
        MATCH (person:Person)-[:WORKED_ON]->(project {id: 'project:soc2-readiness-audit'})
        MATCH (person)-[:MEMBER_OF]->(team)-[:OWNS_SERVICE]->(service)
        RETURN project.name AS project,
               collect(DISTINCT team.name) AS involved_teams,
               collect(DISTINCT service.name) AS owned_services
        """
    if "pricing model" in q and "approved" in q:
        return """
        MATCH (project {id: 'project:pricing-model-redesign'})
        OPTIONAL MATCH (project)-[:PRODUCED_DOCUMENT]->(doc)
        OPTIONAL MATCH (project)-[:MADE_DECISION]->(decision)-[:APPROVED_BY]->(approver)
        OPTIONAL MATCH (person:Person)-[:WORKED_ON]->(project)
        RETURN project.name AS project, project.description AS project_description,
               collect(DISTINCT doc.name) AS documents,
               collect(DISTINCT decision.name) AS decisions,
               collect(DISTINCT approver.name) AS approvers,
               collect(DISTINCT person.name) AS contributors
        """
    if "incidents influenced architecture decisions" in q:
        return """
        MATCH (incident:Incident)-[:INFLUENCED]->(decision:Decision)
        OPTIONAL MATCH (doc)-[:RELATED_TO]->(decision)
        RETURN collect(DISTINCT incident.name) AS incidents,
               collect(DISTINCT decision.name) AS influenced_decisions,
               collect(DISTINCT doc.name) AS related_documents
        """
    if "documents support" in q and "multi-cdn routing" in q:
        return """
        MATCH (decision {id: 'decision:multi-cdn-routing'})
        OPTIONAL MATCH (doc)-[:RELATED_TO]->(decision)
        OPTIONAL MATCH (project)-[:MADE_DECISION]->(decision)
        OPTIONAL MATCH (incident)-[:INFLUENCED]->(decision)
        RETURN decision.name AS decision, decision.description AS decision_description,
               collect(DISTINCT doc.name) AS supporting_documents,
               collect(DISTINCT project.name) AS projects,
               collect(DISTINCT incident.name) AS influencing_incidents
        """
    if "consulted for billing platform changes" in q:
        return """
        MATCH (team {id: 'team:billing-platform'})-[:OWNS_SERVICE]->(service)
        OPTIONAL MATCH (person:Person)-[:MEMBER_OF]->(team)
        OPTIONAL MATCH (doc {id: 'document:billing-platform-runbook'})
        RETURN team.name AS owner_team,
               collect(DISTINCT person.name) AS people_to_consult,
               collect(DISTINCT service.name) AS owned_services,
               doc.name AS runbook, doc.description AS runbook_description
        """
    if "projects involved both security and platform engineering" in q:
        return """
        MATCH (security_person:Person)-[:MEMBER_OF]->(:Team {id: 'team:security-governance'})
        MATCH (platform_person:Person)-[:MEMBER_OF]->(:Team {id: 'team:platform-engineering'})
        MATCH (security_person)-[:WORKED_ON]->(project)<-[:WORKED_ON]-(platform_person)
        RETURN project.name AS project,
               collect(DISTINCT security_person.name) AS security_people,
               collect(DISTINCT platform_person.name) AS platform_people
        """

    return None


def is_all_services_oncall_query(query: str) -> bool:
    q = query.lower()
    return ("oncall" in q or "on-call" in q) and ("today" in q or "schedule" in q) and "playback" not in q


def extract_service_names_from_oncall_query(query: str) -> list[str]:
    q = query.lower()
    if not ("oncall" in q or "on-call" in q):
        return []
    matches = re.findall(r'\b([a-z0-9][a-z0-9-]*service)\b', q)
    seen = []
    for match in matches:
        if match not in seen:
            seen.append(match)
    return seen


def extract_service_name_from_oncall_query(query: str) -> Optional[str]:
    names = extract_service_names_from_oncall_query(query)
    return re.escape(names[0]) if names else None


def is_single_service_oncall_query(query: str) -> bool:
    return bool(extract_service_names_from_oncall_query(query))


def extract_service_names_from_dashboard_query(query: str) -> list[str]:
    q = query.lower()
    if "dashboard" not in q:
        return []
    matches = re.findall(r'\b([a-z0-9][a-z0-9-]*service)\b', q)
    seen = []
    for match in matches:
        if match not in seen:
            seen.append(match)
    return seen


def is_service_dashboard_query(query: str) -> bool:
    return bool(extract_service_names_from_dashboard_query(query))


def is_missing_dashboard_query(query: str) -> bool:
    q = query.lower()
    return "dashboard" in q and ("missing" in q or "without" in q)


def is_live_telemetry_query(query: str) -> bool:
    q = query.lower()
    live_terms = [
        "live", "right now", "current", "cpu", "memory", "latency now",
        "real-time", "realtime", "burn rate", "error budget",
    ]
    return any(term in q for term in live_terms) and any(
        service in q for service in ["service", "playback", "billing", "identity", "observability", "ml-ranking"]
    )


def format_live_telemetry_unavailable(query: str, mode: str) -> str:
    return (
        f"{mode} cannot answer this from the current dataset.\n\n"
        "The demo uses static synthetic organizational data: services, owners, runbooks, dashboards, "
        "SLOs, on-call schedules, incidents, and relationships. It does not ingest live metrics, "
        "APM samples, Prometheus series, Grafana panel values, real-time CPU usage, or "
        "current error-budget burn rates.\n\n"
        f"Question asked: {query}\n\n"
        "To answer this in a production system, NexusGraph would need a live telemetry connector "
        "for a source such as Prometheus, Grafana, Datadog, New Relic, or CloudWatch."
    )


def is_service_runbook_query(query: str) -> bool:
    q = query.lower()
    return "runbook" in q and "cover" in q and any(
        service in q for service in ["billing", "playback", "identity", "recommendation", "observability"]
    )


RELATIONSHIP_RETURN_PATTERN = re.compile(
    r'MATCH\s+\((\w+)(:[^)]+)?\)-\[(.*?)\]-\((\w+)(:[^)]+)?\)\s+(WHERE\s+.*?)\s+RETURN\s+.*',
    re.IGNORECASE | re.DOTALL,
)


def enhance_relationship_cypher(cypher: str) -> str:
    """Return path nodes and relationship types for multi-hop relationship queries."""
    if "relationships(path)" in cypher or "nodes(path)" in cypher:
        return cypher

    match = RELATIONSHIP_RETURN_PATTERN.search(cypher)
    if not match:
        return cypher

    left_alias, left_label, rel_pattern, right_alias, right_label, where_clause = match.groups()
    if left_label == ":Person" and right_label == ":Service":
        rel_pattern = "*1..3"
    elif "[*" not in cypher:
        return cypher

    return (
        f"MATCH path=({left_alias}{left_label or ''})-[{rel_pattern}]-({right_alias}{right_label or ''}) "
        f"{where_clause} "
        "RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS nodes, "
        "[r IN relationships(path) | type(r)] AS relationships "
        "LIMIT 10"
    )


def format_graph_results(results: list[dict]) -> str:
    if not results:
        return "No matching relationships found in the graph."

    path_lines = []
    other_rows = []
    for row in results:
        nodes = row.get("nodes")
        relationships = row.get("relationships")
        if isinstance(nodes, list) and isinstance(relationships, list) and len(nodes) == len(relationships) + 1:
            parts = [str(nodes[0])]
            for rel, node in zip(relationships, nodes[1:]):
                parts.append(f"-[{rel}]-")
                parts.append(str(node))
            path_lines.append(" ".join(parts))
        else:
            other_rows.append(row)

    if path_lines:
        return "Relationship paths found:\n" + "\n".join(f"- {line}" for line in path_lines)
    return f"Graph results found: {str(other_rows)}"


def format_oncall_schedule(results: list[dict]) -> str:
    sorted_rows = sorted(results, key=lambda row: str(row.get("service", "")))
    direct_count = sum(
        1 for row in sorted_rows
        if row.get("schedule") != "No direct service on-call schedule modeled"
    )
    fallback_count = len(sorted_rows) - direct_count

    lines = [
        "Today's on-call schedule across Streamflix services:",
        "",
        f"Direct service schedules: {direct_count}",
        f"Owner-team fallback rows: {fallback_count}",
        "",
        "| Service | Schedule | Primary engineer | Secondary engineer | Owner / escalation team |",
        "|---|---|---|---|---|",
    ]
    for row in sorted_rows:
        lines.append(
            "| {service} | {schedule} | {primary} | {secondary} | {owner} |".format(
                service=row.get("service", "Unknown"),
                schedule=row.get("schedule", "Not modeled"),
                primary=row.get("primary_oncall", "Not modeled"),
                secondary=row.get("secondary_oncall", "Not modeled"),
                owner=row.get("owner_team", "Not modeled"),
            )
        )

    lines.extend([
        "",
        "Rows marked `Escalate to owner team` mean the synthetic dataset has an owner team and runbook for the service,",
        "but does not model named primary/secondary engineers for that imported service.",
    ])
    return "\n".join(lines)


def format_single_service_oncall(results: list[dict]) -> str:
    if not results:
        return "No matching service was found in the graph."

    lines = [
        "On-call coverage for requested services:",
        "",
        "| Service | Direct schedule | Primary engineer | Secondary engineer | Owner / escalation team |",
        "|---|---|---|---|---|",
    ]
    has_fallback = False
    for row in sorted(results, key=lambda item: str(item.get("service", ""))):
        service = row.get("service", "Unknown service")
        schedule = row.get("schedule", "No direct service on-call schedule modeled")
        primary = row.get("primary_oncall", "Escalate to owner team")
        secondary = row.get("secondary_oncall", "Escalate to owner team")
        owner = row.get("owner_team", "No owner modeled")
        if schedule == "No direct service on-call schedule modeled":
            has_fallback = True
        lines.append(f"| {service} | {schedule} | {primary} | {secondary} | {owner} |")

    lines.append("")
    if has_fallback:
        lines.append(
            "Rows without a direct schedule should use the owner team escalation path instead of "
            "inheriting a downstream or upstream service schedule."
        )
    else:
        lines.append("Source: direct `Service -> HAS_ONCALL_SCHEDULE -> OnCallSchedule` graph relationships.")
    return "\n".join(lines)


def format_service_dashboards(results: list[dict]) -> str:
    if not results:
        return "No matching services were found in the graph."

    lines = [
        "Dashboard coverage for requested services:",
        "",
        "| Service | Dashboard | What it monitors | Owner team |",
        "|---|---|---|---|",
    ]
    missing = False
    for row in sorted(results, key=lambda item: str(item.get("service", ""))):
        dashboard = row.get("dashboard", "No dashboard coverage modeled")
        if dashboard == "No dashboard coverage modeled":
            missing = True
        lines.append(
            "| {service} | {dashboard} | {description} | {owner} |".format(
                service=row.get("service", "Unknown service"),
                dashboard=dashboard,
                description=row.get("dashboard_description", "No dashboard description modeled"),
                owner=row.get("owner_team", "No owner modeled"),
            )
        )
    lines.append("")
    if missing:
        lines.append("Rows without dashboard coverage should be assigned to the owner team for catalog follow-up.")
    else:
        lines.append("Source: direct `Service -> HAS_DASHBOARD -> Dashboard` graph relationships.")
    return "\n".join(lines)


def format_missing_dashboards(results: list[dict]) -> str:
    if not results:
        return "Every service in the catalog has dashboard coverage modeled."

    lines = [
        "Services missing dashboard coverage:",
        "",
        "| Service | Owner team | Description |",
        "|---|---|---|",
    ]
    for row in results:
        lines.append(
            "| {service} | {owner} | {description} |".format(
                service=row.get("service", "Unknown service"),
                owner=row.get("owner_team", "No owner modeled"),
                description=row.get("description", ""),
            )
        )
    return "\n".join(lines)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def format_service_runbooks(results: list[dict]) -> str:
    if not results:
        return "No service runbooks were found in the graph."

    row = results[0]
    service = row.get("service", "service")
    runbooks = _as_list(row.get("runbooks") or row.get("runbook"))
    descriptions = _as_list(row.get("runbook_descriptions") or row.get("runbook_description"))
    dashboards = _as_list(row.get("dashboards"))
    slos = _as_list(row.get("slos"))
    schedules = _as_list(row.get("schedules"))

    lines = [f"{service} runbooks:", ""]
    for index, runbook in enumerate(runbooks):
        description = descriptions[index] if index < len(descriptions) else "No description modeled"
        lines.append(f"- **{runbook}**: {description}")

    if dashboards:
        lines.append(f"- Related dashboards: {', '.join(str(item) for item in dashboards if item)}")
    if slos:
        lines.append(f"- Related SLOs: {', '.join(str(item) for item in slos if item)}")
    if schedules:
        lines.append(f"- On-call schedules: {', '.join(str(item) for item in schedules if item)}")

    lines.append("")
    lines.append("Source: knowledge graph service-to-runbook relationships.")
    return "\n".join(lines)


def router(state: State) -> dict:
    """Decide whether to use vector, graph, or compare."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert router. You decide whether a query should be answered using a Vector Store, a Knowledge Graph, or both.\n"
                   "Rules:\n"
                   "1. Use 'vector' for descriptive, general knowledge, or 'what is' questions that don't imply complex relationships.\n"
                   "2. Use 'graph' for questions about relationships, paths, connections, or 'how is X related to Y'.\n"
                   "3. Use 'compare' if the query involves both or requires a comprehensive answer from both sources.\n"
                   "Respond with ONLY the word 'vector', 'graph', or 'compare'."),
        ("human", "{query}")
    ])
    chain = prompt | llm
    response = chain.invoke({"query": state["query"]})
    route = response.content.strip().lower()
    
    # Validation
    if "compare" in route:
        route = "compare"
    elif "graph" in route:
        route = "graph"
    else:
        route = "vector"
        
    return {"route": route, "token_usage": extract_token_usage(response)}

def vector_node(state: State) -> dict:
    """Query the vector store and return semantic evidence."""
    t0 = time.perf_counter()
    results = query_vector_store(state["query"])
    matches = results["matches"]
    context = [f"Vector Store: {m['document']}" for m in matches]
    evidence = [
        {
            "source": match.get("metadata", {}).get("source", "unknown"),
            "kind": match.get("metadata", {}).get("kind", "unknown"),
            "distance": match.get("distance"),
            "metadata": match.get("metadata", {}),
            "text": match.get("document", ""),
        }
        for match in matches
    ]
    trace = empty_trace("vector")
    trace["stages"].append(make_trace_stage(
        "Vector retrieval",
        "complete",
        f"Retrieved {len(matches)} semantic chunks from ChromaDB.",
        elapsed=time.perf_counter() - t0,
        details={"match_count": len(matches)},
    ))
    trace["evidence"]["vector"] = evidence
    return {"context": context, "trace": trace}

def graph_node(state: State) -> dict:
    """Query the knowledge graph manually with cleaning."""
    t0 = time.perf_counter()
    if is_live_telemetry_query(state["query"]):
        trace = empty_trace("graph")
        trace["stages"].append(make_trace_stage(
            "Graph retrieval",
            "unavailable",
            "Live telemetry is not present in the static synthetic graph.",
            elapsed=time.perf_counter() - t0,
            details={"row_count": 0, "deterministic": True, "token_usage": EMPTY_TOKEN_USAGE},
        ))
        trace["known_gaps"].append("No live telemetry connector is configured for CPU, memory, or real-time metrics.")
        answer = format_live_telemetry_unavailable(state["query"], "GraphRAG")
        return {
            "context": [f"Graph Analysis: {answer}"],
            "answer": answer,
            "token_usage": add_token_usage(state.get("token_usage"), EMPTY_TOKEN_USAGE),
            "trace": trace,
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Neo4j expert. Generate a simple, valid Cypher query. NO text other than the query."),
        ("human", CYPHER_GENERATION_TEMPLATE)
    ])
    chain = prompt | llm
    token_usage = EMPTY_TOKEN_USAGE
    direct_answer = None
    cypher = ""
    used_deterministic_cypher = False
    
    try:
        neo4j_graph = get_graph()
        deterministic_cypher = deterministic_cypher_for_query(state["query"])
        used_deterministic_cypher = bool(deterministic_cypher)
        if deterministic_cypher:
            cypher = " ".join(deterministic_cypher.split())
        else:
            # 1. Generate
            schema = neo4j_graph.get_schema
            cypher_response = chain.invoke({"question": state["query"], "schema": schema})
            token_usage = extract_token_usage(cypher_response)
            raw_cypher = cypher_response.content
            
            # 2. Clean
            cypher = clean_cypher(raw_cypher)

        if not used_deterministic_cypher:
            # 3. Rewrite exact-match property filters into WHERE ... =~ clauses
            rewritten = rewrite_property_filters(cypher)
            if rewritten != cypher:
                print(f"--- REWROTE CYPHER ---\nFrom: {cypher}\nTo:   {rewritten}\n-----------------------")
                cypher = rewritten

            enhanced = enhance_relationship_cypher(cypher)
            if enhanced != cypher:
                print(f"--- ENHANCED CYPHER ---\nFrom: {cypher}\nTo:   {enhanced}\n-----------------------")
                cypher = enhanced

        # 4. Guard against destructive statements before execution
        if not cypher or not is_read_only(cypher):
            print(f"--- REJECTED CYPHER (write clause detected) ---\n{cypher}\n-----------------------")
            trace = empty_trace("graph")
            trace["stages"].append(make_trace_stage(
                "Graph retrieval",
                "rejected",
                "Generated Cypher was rejected as unsafe or empty.",
                elapsed=time.perf_counter() - t0,
                details={"cypher": cypher},
            ))
            trace["known_gaps"].append("Graph query was rejected before execution because it was unsafe or empty.")
            return {
                "context": ["Graph Analysis: Generated query was rejected as unsafe or empty."],
                "token_usage": add_token_usage(state.get("token_usage"), token_usage),
                "trace": trace,
            }

        print(f"--- EXECUTING CYPHER ---\n{cypher}\n-----------------------")

        # 5. Execute
        results = neo4j_graph.query(cypher)
        graph_evidence = {
            "cypher": cypher,
            "row_count": len(results),
            "rows": results,
            "deterministic": used_deterministic_cypher,
        }
        trace = empty_trace("graph")
        trace["stages"].append(make_trace_stage(
            "Graph retrieval",
            "complete",
            f"Returned {len(results)} rows from Neo4j.",
            elapsed=time.perf_counter() - t0,
            details={
                "row_count": len(results),
                "deterministic": used_deterministic_cypher,
                "token_usage": token_usage,
                "token_stage": "Text-to-Cypher" if not used_deterministic_cypher else "Deterministic Cypher template",
            },
        ))
        trace["evidence"]["graph"] = [graph_evidence]
        if is_all_services_oncall_query(state["query"]):
            direct_answer = format_oncall_schedule(results)
            trace["known_gaps"].append(
                "On-call data is static synthetic data; rows without named engineers use owner-team escalation."
            )
        elif is_single_service_oncall_query(state["query"]):
            direct_answer = format_single_service_oncall(results)
            trace["known_gaps"].append(
                "On-call data is static synthetic data. Direct service schedules are not inherited through dependency paths."
            )
        elif is_service_dashboard_query(state["query"]):
            direct_answer = format_service_dashboards(results)
        elif is_missing_dashboard_query(state["query"]):
            direct_answer = format_missing_dashboards(results)
        elif is_service_runbook_query(state["query"]):
            direct_answer = format_service_runbooks(results)
        else:
            direct_answer = None
        graph_answer = direct_answer or format_graph_results(results)
            
    except Exception as e:
        graph_answer = f"Error querying graph. Check logs for details."
        trace = empty_trace("graph")
        trace["stages"].append(make_trace_stage(
            "Graph retrieval",
            "error",
            "Graph query failed before a trusted result could be returned.",
            elapsed=time.perf_counter() - t0,
            details={"error": str(e), "cypher": cypher},
        ))
        trace["known_gaps"].append("Graph evidence is unavailable because the Neo4j query failed.")
        print(f"DEBUG Graph Error: {str(e)}")
    
    result = {
        "context": [f"Graph Analysis: {graph_answer}"],
        "token_usage": add_token_usage(state.get("token_usage"), token_usage),
        "trace": trace,
    }
    if direct_answer:
        result["answer"] = direct_answer
    return result

def synthesizer_node(state: State) -> dict:
    """Generate final grounded answer with citations."""
    full_context = "\n\n".join(state["context"])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer the user query using ONLY the provided context. "
                   "If the context doesn't contain the answer, say you don't know. "
                   "IMPORTANT: Distinguish between 'Vector Store' context and 'Graph Analysis' context. "
                   "For hybrid answers, explicitly combine what the vector context contributes with what the graph context contributes; "
                   "do not simply repeat the graph answer when vector context is present. "
                   "If vector context lacks a relationship but graph context has graph results, say vector retrieval did not provide document evidence "
                   "and then explain what the graph found as the authoritative relationship evidence. "
                   "Never conclude that no relationship exists when Graph Analysis contains relationship paths. "
                   "When Graph Analysis contains relationship paths, preserve the path chain and relationship names; do not invert edge direction or invent a role. "
                   "Cite your sources (e.g., 'According to the knowledge graph...', 'The vector documentation states...') "
                   "Provide a concise and accurate answer based on the retrieved information."),
        ("human", "Context: {context}\n\nQuery: {query}\n\nAnswer:")
    ])
    chain = prompt | llm
    response = chain.invoke({"query": state["query"], "context": full_context})
    return {
        "answer": response.content,
        "token_usage": add_token_usage(state.get("token_usage"), extract_token_usage(response)),
    }

# Build the graph
workflow = StateGraph(State)

workflow.add_node("router", router)
workflow.add_node("vector_node", vector_node)
workflow.add_node("graph_node", graph_node)
workflow.add_node("synthesizer_node", synthesizer_node)

workflow.set_entry_point("router")

def route_decision(state: State):
    if state["route"] == "vector":
        return "vector_node"
    elif state["route"] == "graph":
        return "graph_node"
    else: # compare
        return "vector_node"

workflow.add_conditional_edges(
    "router",
    route_decision,
    {
        "vector_node": "vector_node",
        "graph_node": "graph_node"
    }
)

def after_vector_decision(state: State):
    if state["route"] == "compare":
        return "graph_node"
    return "synthesizer_node"

workflow.add_conditional_edges(
    "vector_node",
    after_vector_decision,
    {
        "graph_node": "graph_node",
        "synthesizer_node": "synthesizer_node"
    }
)

workflow.add_edge("graph_node", "synthesizer_node")
workflow.add_edge("synthesizer_node", END)

# Compile
app = workflow.compile()

def _run(state: dict) -> dict:
    """Execute nodes directly without router, given a pre-set route."""
    state.setdefault("token_usage", EMPTY_TOKEN_USAGE.copy())
    if state["route"] == "vector" and is_live_telemetry_query(state["query"]):
        answer = format_live_telemetry_unavailable(state["query"], "Vector RAG")
        trace = empty_trace("vector")
        trace["stages"].append(make_trace_stage(
            "Vector retrieval",
            "unavailable",
            "Live telemetry is not present in the static synthetic vector store.",
            details={"match_count": 0},
        ))
        trace["known_gaps"].append("No live telemetry connector is configured for CPU, memory, or real-time metrics.")
        return {
            "answer": answer,
            "route": state["route"],
            "token_usage": EMPTY_TOKEN_USAGE,
            "trace": trace,
            "structured": structured_payload(state["query"], state["route"], answer, trace, EMPTY_TOKEN_USAGE),
        }

    trace_parts = []
    if state["route"] in ("vector", "compare"):
        vector_result = vector_node(state)
        state["context"].extend(vector_result.get("context", []))
        trace_parts.append(vector_result.get("trace"))
    if state["route"] in ("graph", "compare"):
        graph_result = graph_node(state)
        state["context"].extend(graph_result.get("context", []))
        state["token_usage"] = graph_result.get("token_usage", state["token_usage"])
        trace_parts.append(graph_result.get("trace"))
        if graph_result.get("answer") and (
            is_all_services_oncall_query(state["query"])
            or is_single_service_oncall_query(state["query"])
            or is_service_dashboard_query(state["query"])
            or is_missing_dashboard_query(state["query"])
            or is_service_runbook_query(state["query"])
            or is_live_telemetry_query(state["query"])
        ):
            state["answer"] = graph_result["answer"]
            trace_mode = "hybrid" if state["route"] == "compare" else state["route"]
            trace = merge_traces(trace_mode, *trace_parts)
            trace["stages"].append(make_trace_stage(
                "Synthesis",
                "skipped",
                "Used deterministic graph answer to avoid unnecessary generation.",
                details={"direct_answer": True, "token_usage": EMPTY_TOKEN_USAGE},
            ))
            return {
                "answer": state["answer"],
                "route": state["route"],
                "token_usage": state["token_usage"],
                "trace": trace,
                "structured": structured_payload(
                    state["query"],
                    state["route"],
                    state["answer"],
                    trace,
                    state["token_usage"],
                ),
            }
    t0 = time.perf_counter()
    state.update(synthesizer_node(state))
    trace_mode = "hybrid" if state["route"] == "compare" else state["route"]
    trace = merge_traces(trace_mode, *trace_parts)
    trace["stages"].append(make_trace_stage(
        "Synthesis",
        "complete",
        "Generated grounded answer from retrieved context.",
        elapsed=time.perf_counter() - t0,
        details={"context_items": len(state.get("context", [])), "token_usage": state.get("token_usage", EMPTY_TOKEN_USAGE)},
    ))
    return {
        "answer": state["answer"],
        "route": state["route"],
        "token_usage": state["token_usage"],
        "trace": trace,
        "structured": structured_payload(
            state["query"],
            state["route"],
            state["answer"],
            trace,
            state["token_usage"],
        ),
    }


def run_vector_rag(query: str) -> dict:
    return _run({"query": query, "context": [], "route": "vector", "answer": None})


def run_graph_rag(query: str) -> dict:
    return _run({"query": query, "context": [], "route": "graph", "answer": None})


def run_hybrid_rag(query: str) -> dict:
    return _run({"query": query, "context": [], "route": "compare", "answer": None})

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Who works on the audit project?"
    
    print(f"--- Querying Hybrid RAG: {query} ---")
    
    inputs = {"query": query, "context": []}
    for output in app.stream(inputs):
        for key, value in output.items():
            print(f"\n[Node: {key}]")
            if "route" in value:
                print(f"Decision: {value['route']}")
            if "answer" in value:
                print(f"Final Answer: {value['answer']}")
    print("\n--- Done ---")
