from __future__ import annotations

import json
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import sys
import os
from pyvis.network import Network

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))


def hydrate_streamlit_secrets() -> None:
    """Expose Streamlit Cloud secrets as env vars before backend modules import."""
    keys = [
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "GOOGLE_API_KEY",
        "GOOGLE_MODEL",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEXUSGRAPH_AUTO_IMPORT_NEO4J",
    ]
    try:
        secrets = st.secrets
    except Exception:
        return
    for key in keys:
        try:
            value = secrets.get(key)
        except Exception:
            value = None
        if value and not os.getenv(key):
            os.environ[key] = str(value)


hydrate_streamlit_secrets()

import chromadb
from software_catalog import build_software_catalog
from ui_trace import evidence_counts, format_stage_elapsed

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Demo queries — GraphRAG focused
# ---------------------------------------------------------------------------
DEMO_QUERIES = [
    {"icon": "VS",
     "query": "What does the billing service runbook cover?",
     "insight": "Vector baseline should do well: semantic retrieval over runbook/document chunks."},
    {"icon": "KG",
     "query": "Who is oncall for ml-ranking-service and observability-service?",
     "insight": "GraphRAG should do well: exact service → schedule/owner relationships."},
    {"icon": "GT",
     "query": "What is the current error budget burn rate for playback-service?",
     "insight": "Both should be honest about the gap: the graph has SLO definitions, but no live burn-rate telemetry feed."},
]

MAX_QUERY_LENGTH = 500

NODE_COLORS = {
    'Person': '#4C9AFF', 'Team': '#79E2F2', 'Project': '#F2A65A',
    'Service': '#F26B6B', 'Skill': '#9C88FF', 'Tool': '#52C97E',
    'Document': '#FFD93D', 'Decision': '#C77DFF', 'Incident': '#FF6B9D',
    'Audit': '#A0A0A0', 'System': '#6BCB77', 'OnCallSchedule': '#4D96FF',
    'EscalationPolicy': '#FFA45B',
}

# Shared design tokens for the custom-HTML panels (incident command center,
# store overview, evidence cards). Each components.html() call renders in its
# own iframe, so this block is re-emitted into every panel rather than shared
# via a single page-level stylesheet. --accent-hybrid is reserved for the
# Hybrid RAG panel (T2).
DESIGN_TOKENS_CSS = """
<style>
  :root {
    --bg-panel: rgba(15, 23, 42, 0.86);
    --bg-card: #0b1220;
    --border: #334155;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
    --accent-indigo: #312e81;
    --accent-emerald: #064e3b;
    --accent-amber: #7c2d12;
    --accent-hybrid: #1d4ed8;
  }
</style>
"""


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def summarize_backend_error(error: Exception) -> str:
    message = str(error)
    lower = message.lower()
    if "resource_exhausted" in lower or "quota exceeded" in lower or "429" in lower:
        provider = os.getenv("LLM_PROVIDER", "configured LLM")
        return (
            f"{provider} quota is exhausted. Add billing/quota for that provider, "
            "or switch Streamlit secrets to another hosted LLM provider such as Groq or OpenAI."
        )
    if "api_key" in lower or "unauthorized" in lower or "permission_denied" in lower or "401" in lower or "403" in lower:
        return "LLM provider authentication failed. Check the API key and selected LLM_PROVIDER in Streamlit secrets."
    if "could not connect to neo4j" in lower or "serviceunavailable" in lower:
        return "Neo4j is unreachable. Check NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, and Aura network availability."
    if "nodename nor servname" in lower or "cannot assign requested address" in lower or "connection" in lower:
        return "A backend service could not be reached from the app runtime. Check hosted service URLs and secrets."
    return "Backend request failed. Check the app logs for the full provider error."


@st.cache_resource(show_spinner=False)
def load_rag_runners() -> dict:
    from hybrid_rag import (
        run_graph_rag,
        run_vector_rag,
    )

    return {"graph": run_graph_rag, "vector": run_vector_rag}


@st.cache_resource(show_spinner=False)
def ensure_runtime_data() -> dict:
    from config import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION
    from vector_ingest import ingest_documents

    status = {"vector_store": "existing", "neo4j_import": "skipped"}
    vector_store_ready = False
    if DEFAULT_CHROMA_PATH.exists():
        try:
            chromadb.PersistentClient(path=str(DEFAULT_CHROMA_PATH)).get_collection(DEFAULT_COLLECTION)
            vector_store_ready = True
        except Exception:
            vector_store_ready = False

    if not vector_store_ready:
        ingest_documents()
        status["vector_store"] = "created"

    if env_flag("NEXUSGRAPH_AUTO_IMPORT_NEO4J"):
        from import_to_neo4j import main as import_to_neo4j

        import_to_neo4j()
        status["neo4j_import"] = "completed"

    return status


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / 'graph' / name)


@st.cache_data
def get_vector_metrics() -> dict:
    client = chromadb.PersistentClient(path=str(ROOT / 'vector_store' / 'chroma'))
    col = client.get_collection('nexusgraph_ai_knowledge')
    meta = col.get(include=['metadatas'])['metadatas']
    from collections import Counter
    kinds = Counter(m.get('kind', 'unknown') for m in meta)
    return {
        "total": col.count(),
        "node_embeddings": kinds.get('graph_node', 0),
        "edge_embeddings": kinds.get('graph_edge', 0),
        "source_artifacts": kinds.get('source_artifact', 0),
    }


def render_graph_view(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> None:
    labels = sorted(nodes_df['label'].unique())
    selected_labels = st.multiselect('Filter by node type', labels, default=labels)
    max_nodes = st.slider('Max nodes to render', min_value=20, max_value=len(nodes_df),
                          value=min(120, len(nodes_df)), step=10)

    filtered_nodes = nodes_df[nodes_df['label'].isin(selected_labels)].head(max_nodes)
    node_ids = set(filtered_nodes['id'])
    filtered_edges = edges_df[edges_df['source'].isin(node_ids) & edges_df['target'].isin(node_ids)]

    if filtered_nodes.empty:
        st.info('No nodes match the selected filters.')
        return

    net = Network(
        height='600px',
        width='100%',
        bgcolor='#0e1117',
        font_color='#fafafa',
        directed=True,
        cdn_resources='remote',
    )
    net.barnes_hut()
    for _, row in filtered_nodes.iterrows():
        if row['label'] == "Person":
            tooltip = (
                f"<b>Person: {row['name']}</b><br>"
                f"Role: {row['description']}<br>"
                f"Employee ID: {row['id']}"
            )
        else:
            tooltip = (
                f"<b>{row['label']}: {row['name']}</b><br>"
                f"Description: {row['description']}<br>"
                f"ID: {row['id']}"
            )
        net.add_node(
            row['id'],
            label=row['name'],
            title=tooltip,
            color=NODE_COLORS.get(row['label'], '#9aa0a6'),
            font={'size': 12, 'color': '#fafafa'},
        )
    for _, row in filtered_edges.iterrows():
        net.add_edge(
            row['source'], row['target'],
            label=row['relationship'],
            title=row['relationship'],
            color='#5f6368',
            font={'size': 9, 'color': '#aaaaaa', 'align': 'middle'},
        )

    components.html(net.generate_html(notebook=False), height=620, scrolling=True)
    st.caption(f"Showing {len(filtered_nodes)} nodes and {len(filtered_edges)} relationships.")


def format_token_usage(token_usage: dict | None) -> str:
    token_usage = token_usage or {}
    input_tokens = int(token_usage.get("input_tokens", 0))
    output_tokens = int(token_usage.get("output_tokens", 0))
    total_tokens = int(token_usage.get("total_tokens", input_tokens + output_tokens))
    return f"Tokens: {total_tokens:,} total ({input_tokens:,} in / {output_tokens:,} out)"


def estimate_tokens(value: object) -> int:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return len(re.findall(r"\w+|[^\w\s]", text))


def graph_workload_token_estimate(result: dict) -> dict:
    trace = result.get("trace") or {}
    evidence = trace.get("evidence", {})
    graph_items = evidence.get("graph", [])
    cypher_text = "\n".join(item.get("cypher", "") for item in graph_items)
    rows = []
    for item in graph_items:
        rows.extend(item.get("rows", []))
    query = (result.get("structured") or {}).get("query", "")
    answer = result.get("answer", "")
    return {
        "query_tokens": estimate_tokens(query),
        "cypher_tokens": estimate_tokens(cypher_text),
        "result_tokens": estimate_tokens(rows),
        "answer_tokens": estimate_tokens(answer),
        "row_count": sum(int(item.get("row_count", 0)) for item in graph_items),
    }


def render_usage_metrics(result: dict, label: str) -> None:
    token_usage = result.get("token_usage") or {}
    input_tokens = int(token_usage.get("input_tokens", 0))
    output_tokens = int(token_usage.get("output_tokens", 0))
    total_tokens = int(token_usage.get("total_tokens", input_tokens + output_tokens))
    if label == "graph":
        workload = graph_workload_token_estimate(result)
        estimated_total = (
            workload["query_tokens"]
            + workload["cypher_tokens"]
            + workload["result_tokens"]
            + workload["answer_tokens"]
        )
        cols = st.columns(4)
        cols[0].metric("Latency", f"{result.get('elapsed', 0):.2f}s")
        cols[1].metric("LLM Tokens", f"{total_tokens:,}")
        cols[2].metric("GraphRAG Tokens", f"{estimated_total:,}")
        cols[3].metric("Graph Rows", f"{workload['row_count']:,}")
    else:
        cols = st.columns(4)
        cols[0].metric("Latency", f"{result.get('elapsed', 0):.2f}s")
        cols[1].metric("Input Tokens", f"{input_tokens:,}")
        cols[2].metric("Output Tokens", f"{output_tokens:,}")
        cols[3].metric("Total Tokens", f"{total_tokens:,}")
    if label == "graph":
        trace = result.get("trace") or {}
        stages = trace.get("stages", [])
        graph_stage = next((stage for stage in stages if stage.get("name") == "Graph retrieval"), {})
        synthesis_stage = next((stage for stage in stages if stage.get("name") == "Synthesis"), {})
        graph_details = graph_stage.get("details", {})
        synthesis_details = synthesis_stage.get("details", {})
        text_to_cypher_usage = graph_details.get("token_usage", {})
        synthesis_usage = synthesis_details.get("token_usage", {})
        breakdown = pd.DataFrame([
            {
                "Stage": "Routing",
                "LLM Input": 0,
                "LLM Output": 0,
                "LLM Total": 0,
                "Estimated Workload Tokens": workload["query_tokens"],
                "Note": "UI-selected GraphRAG route; query text still contributes workload tokens",
            },
            {
                "Stage": graph_details.get("token_stage", "Text-to-Cypher"),
                "LLM Input": int(text_to_cypher_usage.get("input_tokens", 0)),
                "LLM Output": int(text_to_cypher_usage.get("output_tokens", 0)),
                "LLM Total": int(text_to_cypher_usage.get("total_tokens", 0)),
                "Estimated Workload Tokens": workload["cypher_tokens"],
                "Note": "LLM is 0 when a deterministic Cypher template is used",
            },
            {
                "Stage": "Graph result rows",
                "LLM Input": 0,
                "LLM Output": 0,
                "LLM Total": 0,
                "Estimated Workload Tokens": workload["result_tokens"],
                "Note": "Rows returned from Neo4j and rendered into the answer",
            },
            {
                "Stage": "Answer synthesis",
                "LLM Input": int(synthesis_usage.get("input_tokens", 0)),
                "LLM Output": int(synthesis_usage.get("output_tokens", 0)),
                "LLM Total": int(synthesis_usage.get("total_tokens", 0)),
                "Estimated Workload Tokens": workload["answer_tokens"],
                "Note": "LLM is 0 when deterministic graph answer skips synthesis",
            },
        ])
        with st.popover("GraphRAG token breakdown"):
            st.caption("LLM tokens are provider-reported. GraphRAG tokens are estimated from query text, Cypher, graph rows, and rendered answer.")
            st.dataframe(breakdown, width="stretch", hide_index=True)


def render_incident_command_center() -> None:
    components.html(
        DESIGN_TOKENS_CSS + """
        <style>
          .ng-wrap {font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: linear-gradient(135deg, #07111f 0%, #0c1220 48%, #111827 100%);
            border: 1px solid #263244; border-radius: 14px; padding: 18px; color: #e5e7eb; overflow: hidden;}
          .ng-grid {display: grid; grid-template-columns: 1.15fr .85fr; gap: 16px;}
          .ng-title {font-size: 24px; font-weight: 800; margin: 0 0 4px;}
          .ng-sub {color: #9ca3af; font-size: 13px; margin-bottom: 16px;}
          .ng-panel {background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px;}
          .ng-pulse {display:inline-block; width:9px; height:9px; background:#fb923c; border-radius:50%;
            box-shadow:0 0 0 rgba(251,146,60,.75); animation:pulse 1.4s infinite;}
          .ng-metrics {display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-top: 14px;}
          .ng-card {background: var(--bg-card); border:1px solid #1f2937; border-radius:10px; padding:10px; min-height:74px;}
          .ng-label {font-size:11px; color: var(--text-muted); text-transform:uppercase; letter-spacing:.08em;}
          .ng-value {font-size:16px; font-weight:700; color: var(--text-primary); margin-top:6px;}
          .ng-flow {display:grid; gap:10px; margin-top: 8px;}
          .ng-step {display:flex; align-items:center; gap:10px; background:#0b1220; border:1px solid #1f2937; border-radius:10px; padding:9px;}
          .ng-dot {width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-weight:800; font-size:12px;}
          .ng-line {height:8px; background:#1f2937; border-radius:999px; overflow:hidden; margin-top:12px;}
          .ng-fill {height:100%; width:72%; background:linear-gradient(90deg,#22c55e,#14b8a6,#38bdf8); animation:fill 2.6s ease-in-out infinite alternate;}
          @keyframes pulse {0%{box-shadow:0 0 0 0 rgba(251,146,60,.75)} 70%{box-shadow:0 0 0 12px rgba(251,146,60,0)} 100%{box-shadow:0 0 0 0 rgba(251,146,60,0)}}
          @keyframes fill {from{width:42%} to{width:92%}}
          @media (max-width: 780px) {.ng-grid,.ng-metrics{grid-template-columns:1fr}.ng-title{font-size:20px}}
        </style>
        <div class="ng-wrap">
          <div class="ng-grid">
            <div class="ng-panel">
              <div class="ng-title"><span class="ng-pulse"></span> Streamflix Playback Incident Readiness</div>
              <div class="ng-sub">Synthetic enterprise scenario: ask one operational question and watch NexusGraph gather service, runbook, SLO, on-call, and evidence context.</div>
              <div class="ng-line"><div class="ng-fill"></div></div>
              <div class="ng-metrics">
                <div class="ng-card"><div class="ng-label">Service</div><div class="ng-value">playback-service</div></div>
                <div class="ng-card"><div class="ng-label">Responder</div><div class="ng-value">On-call graph</div></div>
                <div class="ng-card"><div class="ng-label">Guidance</div><div class="ng-value">Runbook chunks</div></div>
                <div class="ng-card"><div class="ng-label">Reliability</div><div class="ng-value">SLO + dashboard</div></div>
              </div>
            </div>
            <div class="ng-panel">
              <div class="ng-label">Behind the scenes</div>
              <div class="ng-flow">
                <div class="ng-step"><div class="ng-dot" style="background:#2563eb">1</div><div>Resolve service and intent</div></div>
                <div class="ng-step"><div class="ng-dot" style="background:#0f766e">2</div><div>Select a graph query pattern</div></div>
                <div class="ng-step"><div class="ng-dot" style="background:#7c3aed">3</div><div>Traverse graph relationships</div></div>
                <div class="ng-step"><div class="ng-dot" style="background:#15803d">4</div><div>Answer with graph evidence and gaps</div></div>
              </div>
            </div>
          </div>
        </div>
        """,
        height=315,
    )


def render_rag_mode_explainer() -> None:
    st.subheader('GraphRAG With Vector Baseline')
    rag_cols = st.columns(3)
    with rag_cols[0]:
        st.markdown(
            """
            **Connected Knowledge**

            Streamflix operational knowledge is modeled as entities and relationships:
            services, teams, on-call schedules, runbooks, dashboards, SLOs, incidents,
            documents, and dependencies.
            """
        )
    with rag_cols[1]:
        st.markdown(
            """
            **GraphRAG**

            Answers from exact relationships. Best for service ownership,
            on-call schedules, dependencies, dashboards, SLO links, and catalog completeness.
            The demo shows Cypher, row counts, relationship paths, and result tables.
            """
        )
    with rag_cols[2]:
        st.markdown(
            """
            **Vector RAG Baseline**

            Vector RAG retrieves semantic chunks from ChromaDB. It is useful for document-style
            questions, but it cannot reliably traverse service ownership, on-call, SLO, dashboard,
            and dependency relationships.
            """
        )


def render_tech_stack() -> None:
    st.subheader("Tech Stack")
    stack_cols = st.columns(4)
    stack = [
        ("UI", "Streamlit", "Interactive demo UI and service catalog explorer"),
        ("KG", "Neo4j", "Graph database for organizational relationships"),
        ("VS", "ChromaDB", "Vector database for semantic baseline retrieval"),
        ("LC", "LangChain + LangGraph", "RAG orchestration, routing, and answer synthesis"),
        ("EM", "Sentence Transformers", "Local embeddings for vector chunks"),
        ("LLM", "Ollama / OpenAI / Gemini / Groq", "Configurable LLM provider"),
        ("GV", "PyVis", "Interactive graph visualization"),
        ("DC", "Docker Compose", "Local app, Neo4j, and Ollama runtime"),
    ]
    for index, (icon, name, description) in enumerate(stack):
        with stack_cols[index % len(stack_cols)]:
            st.markdown(
                f"""
                <div style="border:1px solid #263244;border-radius:8px;padding:12px;background:#0f172a;min-height:112px;margin-bottom:10px">
                  <div style="display:flex;align-items:center;gap:10px">
                    <div style="width:34px;height:34px;border-radius:8px;background:#1d4ed8;color:#dbeafe;display:grid;place-items:center;font-size:12px;font-weight:900">{html.escape(icon)}</div>
                    <div style="font-weight:800;color:#f8fafc">{html.escape(name)}</div>
                  </div>
                  <div style="font-size:13px;color:#94a3b8;margin-top:6px">{html.escape(description)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_store_overview(nodes_count: int, relationships_count: int, query_count: int, vector_metrics: dict) -> None:
    cards = [
        ("KG", "Neo4j Graph", f"{nodes_count:,} nodes", f"{relationships_count:,} relationships", "var(--accent-indigo)"),
        ("VS", "ChromaDB Baseline", f"{vector_metrics['total']:,} vectors", f"{vector_metrics['source_artifacts']:,} source artifacts", "var(--accent-emerald)"),
        ("QA", "Demo Query Set", f"{query_count:,} curated questions", "GraphRAG primary + vector baseline", "var(--accent-amber)"),
    ]
    card_html = ""
    for icon, title, primary, secondary, color in cards:
        card_html += f"""
        <div class="store-card" style="background:{color}">
          <div class="store-icon">{html.escape(icon)}</div>
          <div>
            <div class="store-title">{html.escape(title)}</div>
            <div class="store-primary">{html.escape(primary)}</div>
            <div class="store-secondary">{html.escape(secondary)}</div>
          </div>
        </div>
        """
    components.html(
        DESIGN_TOKENS_CSS + f"""
        <style>
          .store-grid {{font-family: ui-sans-serif, system-ui; display:grid; grid-template-columns:repeat(3,1fr); gap:14px;}}
          .store-card {{border:1px solid var(--border); border-radius:12px; padding:16px; color: var(--text-primary); display:flex; gap:14px; align-items:center; min-height:112px; position:relative; overflow:hidden;}}
          .store-card:after {{content:""; position:absolute; inset:auto -20% 0 -20%; height:2px; background:linear-gradient(90deg,transparent,#fff,transparent); animation:sweep 3s linear infinite; opacity:.35;}}
          .store-icon {{width:44px; height:44px; border-radius:10px; background:rgba(255,255,255,.12); display:grid; place-items:center; font-weight:900; letter-spacing:.04em;}}
          .store-title {{font-size:15px; font-weight:800; color:#f8fafc;}}
          .store-primary {{font-size:26px; font-weight:900; margin-top:4px;}}
          .store-secondary {{font-size:12px; color:#cbd5e1; margin-top:2px;}}
          @keyframes sweep {{from{{transform:translateX(-40%)}} to{{transform:translateX(40%)}}}}
          @media (max-width: 860px) {{.store-grid{{grid-template-columns:1fr}}}}
        </style>
        <div class="store-grid">{card_html}</div>
        """,
        height=140,
    )


def render_trace_timeline(trace: dict | None) -> None:
    trace = trace or {}
    stages = trace.get("stages", [])
    if not stages:
        st.info("No execution trace was returned for this run.")
        return

    timeline_cols = st.columns(min(len(stages), 5))
    for index, stage in enumerate(stages):
        col = timeline_cols[index % len(timeline_cols)]
        col.metric(stage.get("name", "Stage"), format_stage_elapsed(stage))
        col.caption(stage.get("summary", "No summary available."))


def render_trace_evidence(trace: dict | None) -> None:
    trace = trace or {}
    counts = evidence_counts(trace)
    mode = trace.get("mode", "graph")
    first_title = "Vector Chunks" if mode == "vector" else "Graph Query"
    first_count = counts["vector"] if mode == "vector" else counts["graph"]
    first_note = "semantic matches" if mode == "vector" else "Cypher result sets"
    second_title = "Source Files" if mode == "vector" else "Relationship Evidence"
    second_count = counts["vector"] if mode == "vector" else counts["graph"]
    second_note = "metadata-backed chunks" if mode == "vector" else "rows, paths, and tables"
    components.html(
        DESIGN_TOKENS_CSS + f"""
        <style>
          .ev-flow {{font-family: ui-sans-serif, system-ui; display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px;}}
          .ev-card {{border-radius:10px; padding:12px; min-height:86px; color:#e5e7eb; border:1px solid var(--border); position:relative; overflow:hidden;}}
          .ev-card:after {{content:""; position:absolute; inset:auto -30% 0 -30%; height:2px; background:linear-gradient(90deg,transparent,#fff,transparent); animation:sweep 2.8s linear infinite; opacity:.45;}}
          .ev-title {{font-weight:800; margin-bottom:8px;}}
          .ev-count {{font-size:28px; font-weight:900;}}
          .ev-note {{font-size:12px; color:#cbd5e1;}}
          @keyframes sweep {{from{{transform:translateX(-40%)}} to{{transform:translateX(40%)}}}}
          @media (max-width: 480px) {{.ev-flow{{grid-template-columns:1fr}}}}
        </style>
        <div class="ev-flow">
          <div class="ev-card" style="background:var(--accent-indigo)"><div class="ev-title">{first_title}</div><div class="ev-count">{first_count}</div><div class="ev-note">{first_note}</div></div>
          <div class="ev-card" style="background:var(--accent-emerald)"><div class="ev-title">{second_title}</div><div class="ev-count">{second_count}</div><div class="ev-note">{second_note}</div></div>
          <div class="ev-card" style="background:var(--accent-amber)"><div class="ev-title">Known Gaps</div><div class="ev-count">{len(trace.get('known_gaps', []))}</div><div class="ev-note">static synthetic data limits</div></div>
        </div>
        """,
        height=330,
    )

    evidence = trace.get("evidence", {})
    tab_evidence, tab_gaps = st.tabs(["Evidence", "Known gaps"])
    with tab_evidence:
        if mode == "vector":
            vector_items = evidence.get("vector", [])
            if vector_items:
                st.dataframe(pd.DataFrame(vector_items), width="stretch")
            else:
                st.info("No vector evidence used.")
        else:
            graph_items = evidence.get("graph", [])
            if graph_items:
                for item in graph_items:
                    st.code(item.get("cypher", "No Cypher captured."), language="cypher")
                    st.write(f"Rows returned: {item.get('row_count', 0)}")
                    rows = item.get("rows", [])
                    if rows:
                        st.dataframe(pd.DataFrame(rows), width="stretch")
            else:
                st.info("No graph evidence used.")
    with tab_gaps:
        gaps = trace.get("known_gaps", [])
        if gaps:
            for gap in gaps:
                st.warning(gap)
        else:
            st.success("No known gaps recorded for this run.")


def catalog_domain(service_name: str) -> str:
    service = service_name.lower()
    if any(term in service for term in ["playback", "manifest", "cdn"]):
        return "Streaming Experience"
    if any(term in service for term in ["billing", "payment", "identity", "audit"]):
        return "Revenue, Identity & Compliance"
    if any(term in service for term in ["recommendation", "feature-store", "ranking", "personalization"]):
        return "Personalization & ML"
    if any(term in service for term in ["observability", "telemetry", "metrics", "logs", "tracing"]):
        return "Platform Operations"
    return "Imported Service Landscape"


def has_catalog_value(value: object) -> bool:
    return bool(value) and str(value) != "Not modeled"


def readiness_items(row: pd.Series) -> list[tuple[str, bool]]:
    return [
        ("Owner", has_catalog_value(row["Owner"])),
        ("On-call", has_catalog_value(row["On-Call Schedule"])),
        ("Runbook", has_catalog_value(row["Runbook"])),
        ("Dashboard", has_catalog_value(row["Dashboard"])),
        ("SLO", has_catalog_value(row["SLO"])),
        ("Env", has_catalog_value(row["Environment"])),
    ]


def readiness_score(row: pd.Series) -> int:
    items = readiness_items(row)
    return round(sum(1 for _, ready in items if ready) / len(items) * 100)


def render_badge(label: str, ready: bool) -> str:
    bg = "#064e3b" if ready else "#3f1d1d"
    border = "#10b981" if ready else "#ef4444"
    color = "#d1fae5" if ready else "#fecaca"
    symbol = "OK" if ready else "Gap"
    return (
        f"<span style='display:inline-block;margin:0 6px 6px 0;padding:4px 8px;"
        f"border-radius:999px;border:1px solid {border};background:{bg};"
        f"color:{color};font-size:12px;font-weight:700'>{html.escape(label)} · {symbol}</span>"
    )


def render_service_card(row: pd.Series) -> None:
    score = readiness_score(row)
    score_color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 50 else "#ef4444"
    badges = "".join(render_badge(label, ready) for label, ready in readiness_items(row))
    service = html.escape(str(row["Service"]))
    description = html.escape(str(row["Description"]))
    owner = html.escape(str(row["Owner"]))
    dependency_count = int(row["Dependency Count"])
    st.markdown(
        f"""
        <div style="border:1px solid #263244;border-radius:8px;padding:14px;background:#0f172a;margin-bottom:12px;min-height:220px">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
            <div>
              <div style="font-size:18px;font-weight:800;color:#f8fafc">{service}</div>
              <div style="font-size:13px;color:#94a3b8;margin-top:2px">{description}</div>
            </div>
            <div style="min-width:58px;text-align:center;border:1px solid {score_color};border-radius:8px;padding:6px;color:{score_color};font-weight:900">
              {score}%
              <div style="font-size:10px;color:#94a3b8;font-weight:600">ready</div>
            </div>
          </div>
          <div style="margin-top:12px;color:#cbd5e1;font-size:13px"><b>Owner:</b> {owner}</div>
          <div style="margin-top:8px;color:#cbd5e1;font-size:13px"><b>Dependencies:</b> {dependency_count}</div>
          <div style="margin-top:12px">{badges}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_service_details(row: pd.Series) -> None:
    detail_cols = st.columns(2)
    with detail_cols[0]:
        st.markdown(f"**Owner:** {row['Owner']}")
        st.markdown(f"**Environment:** {row['Environment']}")
        st.markdown(f"**On-call:** {row['On-Call Schedule']}")
        st.markdown(f"**Dependencies:** {int(row['Dependency Count'])}")
    with detail_cols[1]:
        st.markdown(f"**Runbook:** {row['Runbook']}")
        st.markdown(f"**Dashboard:** {row['Dashboard']}")
        st.markdown(f"**SLO:** {row['SLO']}")
        missing = [label for label, ready in readiness_items(row) if not ready]
        if missing:
            st.warning("Missing catalog signals: " + ", ".join(missing))
        else:
            st.success("All key readiness signals are modeled.")


def render_software_catalog_explorer(catalog_df: pd.DataFrame) -> None:
    catalog = catalog_df.copy()
    catalog["Domain"] = catalog["Service"].map(catalog_domain)
    catalog["Readiness"] = catalog.apply(readiness_score, axis=1)

    summary_cols = st.columns(4)
    summary_cols[0].metric("Services", len(catalog))
    summary_cols[1].metric("Domains", catalog["Domain"].nunique())
    summary_cols[2].metric("Avg Readiness", f"{round(catalog['Readiness'].mean())}%")
    summary_cols[3].metric("With Runbooks", int(catalog["Runbook"].map(has_catalog_value).sum()))

    controls = st.columns([2, 2, 1])
    selected_domains = controls[0].multiselect(
        "Domains",
        sorted(catalog["Domain"].unique()),
        default=sorted(catalog["Domain"].unique()),
    )
    service_filter = controls[1].text_input("Filter services", placeholder="playback, billing, identity...")
    only_gaps = controls[2].checkbox("Show gaps only")

    filtered = catalog[catalog["Domain"].isin(selected_domains)]
    if service_filter:
        filtered = filtered[filtered["Service"].str.contains(service_filter, case=False, na=False)]
    if only_gaps:
        filtered = filtered[filtered["Readiness"] < 100]

    domains = sorted(filtered["Domain"].unique())
    if not domains:
        st.info("No services match the selected catalog filters.")
    else:
        domain_tabs = st.tabs([f"{domain} · {len(filtered[filtered['Domain'] == domain])}" for domain in domains])
        for tab, domain in zip(domain_tabs, domains):
            domain_df = filtered[filtered["Domain"] == domain].sort_values(["Readiness", "Service"], ascending=[True, True])
            with tab:
                st.caption(f"{domain} services")
                rows = list(domain_df.iterrows())
                for start in range(0, len(rows), 3):
                    cols = st.columns(3)
                    for col, (_, row) in zip(cols, rows[start:start + 3]):
                        with col:
                            render_service_card(row)
                            with st.popover("Details", width="stretch"):
                                render_service_details(row)

    if st.checkbox("Show raw catalog data", value=False):
        st.dataframe(catalog.drop(columns=["Domain", "Readiness"]), width="stretch", hide_index=True)


def render_project_story(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> None:
    with st.expander('Overview: Why This Demo Exists', expanded=False):
        st.subheader('Why This Demo Exists')
        render_incident_command_center()
        st.markdown(
            """
            **Streamflix** is an imaginary streaming services company built for this demo.
            It behaves like a real platform organization: customer-facing playback services,
            billing and identity systems, SRE rotations, incident runbooks, dashboards, SLOs,
            audit evidence, architecture decisions, and teams that own different parts of the stack.

            The data shown here is **static synthetic data**. It is intentionally realistic enough
            to demonstrate the retrieval patterns, but it is not connected to live production systems.
            I am using this phase to strengthen the learning and architecture before extending the
            project toward dynamic operational content.

            **NexusGraph** shows how RAG can help when operational knowledge is scattered across
            documents, service catalogs, ownership records, incident notes, runbooks, and graph
            relationships.
            """
        )
        st.image(
            str(ROOT / 'docs' / 'README.gif'),
            caption='Example graph exploration view: operational entities and relationships connected through a service graph.',
            width='stretch',
        )

        c1, c2, c3 = st.columns(3)
        c1.metric('Raw Knowledge Nodes', len(nodes_df))
        c2.metric('Raw Relationships', len(edges_df))
        c3.metric('Knowledge Sources', 'Graph + Docs')

    with st.expander('1. The problem this project is trying to solve'):
        st.markdown(
            """
            During an incident, teams rarely need just one document. They need to know:

            - which service is affected
            - who owns it
            - who is on-call right now
            - which runbook applies
            - which dashboards and SLOs matter
            - which upstream or downstream services are involved
            - which previous incidents or architecture decisions are relevant

            Traditional search can find a matching page, but it does not reliably explain
            relationships like `service -> on-call schedule -> person` or
            `incident -> decision -> supporting document`. That is the gap this project
            demonstrates.
            """
        )

    with st.expander('2. What raw data is loaded into the demo'):
        st.markdown(
            """
            The seed data represents Streamflix organizational knowledge:

            - **People and teams:** engineers, SREs, security, platform, billing, and product teams.
            - **Software catalog:** services such as playback, manifest, CDN routing, billing, identity, and observability.
            - **Operational artifacts:** runbooks, dashboards, SLOs, escalation policies, and on-call schedules.
            - **Business and engineering context:** projects, incidents, architecture decisions, audits, and documents.
            - **Relationships:** ownership, dependencies, on-call assignments, document support, decision approvals, incident impact, and project participation.

            The demo represents this raw knowledge as a **Neo4j graph** so GraphRAG can answer
            relationship-heavy operational questions.

            The graph modeling strategy is deliberately simple for Phase 1:

            - **Graph nodes** represent entities such as services, people, teams, runbooks, dashboards, SLOs, incidents, and environments.
            - **Graph relationships** represent operational facts such as `HAS_RUNBOOK`, `HAS_ONCALL_SCHEDULE`, `HAS_SLO`, `DEPENDS_ON`, and `OWNS_SERVICE`.
            - **Source artifacts** such as YAML, markdown, and CSV files are converted into graph entities and relationships.
            - Each entity keeps identifiers and descriptions so answers can be traced back to the raw synthetic source data.

            This version uses static synthetic data. Future iterations can apply the same graph model
            to dynamic content such as fresh incident notes, changing on-call schedules, updated service
            catalogs, new runbooks, and live telemetry summaries.
            """
        )

    with st.expander('Example: one rich graph data source'):
        st.markdown(
            """
            A useful example is the **Playback Latency Runbook** domain. One raw source says:

            ```yaml
            id: runbook:playback-latency
            type: Runbook
            name: Playback Latency Runbook
            description: Steps for playback latency, CDN failover, and manifest degradation
            ```

            In the **graph database**, that source becomes connected operational knowledge:

            ```text
            service:playback -[HAS_RUNBOOK]-> runbook:playback-latency
            incident:playback-latency-sev1 -[AFFECTED]-> service:playback
            incident:playback-latency-sev1 -[USED_RUNBOOK]-> runbook:playback-latency
            service:playback -[HAS_ONCALL_SCHEDULE]-> oncall:playback-primary
            oncall:playback-primary -[CURRENT_PRIMARY_ONCALL]-> person:emma-chen
            service:playback -[HAS_DASHBOARD]-> dashboard:playback-health
            service:playback -[HAS_SLO]-> slo:playback-start-latency
            ```

            This is better for relationship questions like:
            **"During a playback latency incident, which runbook applies, who is on-call,
            and which dashboard/SLO should I inspect?"**

            The point of GraphRAG here is that the answer is not trapped in a single document.
            It emerges from connected facts across service catalog, on-call, runbook, dashboard,
            SLO, dependency, and incident relationships.
            """
        )

    with st.expander('3. Next iteration: AI Agents for autonomous actions'):
        st.markdown(
            """
            The next phase is not just answering questions. It is moving from retrieval to action.

            Future AI agents could use the same knowledge graph and RAG layer to:

            - inspect the relevant service catalog entry
            - pull the correct runbook and summarize the first remediation steps
            - identify primary and secondary on-call responders
            - notify the right Slack or Teams channel
            - open or enrich an incident ticket
            - check dashboards and SLOs for the affected service
            - gather related architecture decisions and previous incident notes
            - draft a post-incident summary with evidence links

            In short: Phase 1 helps responders **find and understand** the right knowledge.
            Later iterations use AI agents to **coordinate and execute** the next operational steps
            with human approval where needed.
            """
        )

    st.divider()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title='nexusgraph-ai', layout='wide')
st.title('nexusgraph-ai')
st.caption('GraphRAG for Organizational Knowledge and Decision Intelligence')

with st.spinner("Preparing local retrieval stores..."):
    ensure_runtime_data()

nodes = load_csv('nodes.csv')
edges = load_csv('edges.csv')
eval_queries = json.loads((ROOT / 'evaluation' / 'comparison_queries.json').read_text())

if 'active_query' not in st.session_state:
    st.session_state.active_query = DEMO_QUERIES[0]["query"]
if 'pending_query' in st.session_state:
    st.session_state.active_query = st.session_state.pending_query
    del st.session_state.pending_query

# ---------------------------------------------------------------------------
# Ask NexusGraph
# ---------------------------------------------------------------------------
with st.expander("Ask NexusGraph", expanded=True):
    user_query = st.text_input(
        "Enter your question about organizational knowledge:",
        key='active_query',
        max_chars=MAX_QUERY_LENGTH,
        placeholder="e.g., How is Emma Chen related to the playback service?",
    )

    if st.button("Run GraphRAG + Vector Baseline"):
        if user_query and len(user_query) <= MAX_QUERY_LENGTH:
            def timed(fn, q):
                t0 = time.perf_counter()
                result = fn(q)
                result["elapsed"] = time.perf_counter() - t0
                return result

            with st.spinner("Running GraphRAG and Vector baseline..."):
                results = {}
                try:
                    runners = load_rag_runners()
                except Exception as e:
                    error = summarize_backend_error(e)
                    results = {
                        "graph": {"answer": None, "error": error, "route": "graph", "elapsed": 0.0},
                        "vector": {"answer": None, "error": error, "route": "vector", "elapsed": 0.0},
                    }
                else:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {pool.submit(timed, fn, user_query): key for key, fn in runners.items()}
                        for future in as_completed(futures):
                            key = futures[future]
                            try:
                                results[key] = future.result()
                            except Exception as e:
                                results[key] = {"answer": None, "error": summarize_backend_error(e), "route": key, "elapsed": 0.0}

            graph_res = results.get("graph", {})
            vector_res = results.get("vector", {})
            graph_col, vector_col = st.columns([1.2, 1])

            with graph_col:
                st.subheader("GraphRAG Answer")
                if graph_res.get("error"):
                    st.error(f"⚠️ GraphRAG backend unavailable: {graph_res['error']}")
                else:
                    st.markdown(graph_res.get("answer", "No answer returned."))
                render_usage_metrics(graph_res, "graph")
                with st.expander("JSON response", expanded=False):
                    st.json(graph_res.get("structured", {}))
                st.markdown("**Behind the scenes**")
                render_trace_timeline(graph_res.get("trace"))
                render_trace_evidence(graph_res.get("trace"))

            with vector_col:
                st.subheader("Vector RAG Baseline")
                if vector_res.get("error"):
                    st.error(f"⚠️ Vector RAG backend unavailable: {vector_res['error']}")
                else:
                    st.markdown(vector_res.get("answer", "No answer returned."))
                render_usage_metrics(vector_res, "vector")
                with st.expander("JSON response", expanded=False):
                    st.json(vector_res.get("structured", {}))
                st.markdown("**Behind the scenes**")
                render_trace_timeline(vector_res.get("trace"))
                render_trace_evidence(vector_res.get("trace"))

            with st.popover("How to read this comparison"):
                st.markdown(
                    """
                    **GraphRAG** is the primary project implementation. It is expected to perform best on
                    relationship-heavy questions such as ownership, on-call schedules, service dependencies,
                    dashboard/SLO links, and catalog completeness.

                    **Vector RAG** is included as a baseline. It retrieves semantically similar chunks from
                    ChromaDB and is useful for document-style questions, but it may miss relationship paths
                    that are explicit in Neo4j.
                    """
                )
        else:
            st.warning(f"Please enter a query between 1 and {MAX_QUERY_LENGTH} characters.")

with st.expander("GraphRAG Demo Queries", expanded=True):
    st.caption('Pick one curated graph relationship query.')

    query_cols = st.columns(3)
    for i, item in enumerate(DEMO_QUERIES):
        with query_cols[i]:
            st.markdown(
                f"""
                <div style="border:1px solid #263244;border-radius:8px;padding:12px;background:#0f172a;min-height:128px;margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                    <div style="width:34px;height:34px;border-radius:8px;background:#312e81;color:#ddd6fe;display:grid;place-items:center;font-size:12px;font-weight:900">{html.escape(item['icon'])}</div>
                    <div style="font-weight:800;color:#f8fafc">Query {i + 1}</div>
                  </div>
                  <div style="font-size:14px;color:#e5e7eb;line-height:1.35">{html.escape(item['query'])}</div>
                  <div style="font-size:12px;color:#94a3b8;margin-top:8px">{html.escape(item['insight'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Use query", key=f"graph_query_{i}", width='stretch'):
                st.session_state.pending_query = item['query']
                st.rerun()

render_project_story(nodes, edges)

with st.expander("Architecture, Stores, And Tech Stack", expanded=False):
    vec = get_vector_metrics()
    st.subheader("Knowledge Stores")
    render_store_overview(len(nodes), len(edges), len(DEMO_QUERIES), vec)
    render_tech_stack()
    render_rag_mode_explainer()

with st.expander("Graph Shape", expanded=False):
    left, right = st.columns(2)
    with left:
        st.dataframe(nodes['label'].value_counts().rename_axis('node_type').reset_index(name='count'), width='stretch')
    with right:
        st.dataframe(edges['relationship'].value_counts().rename_axis('relationship').reset_index(name='count'), width='stretch')

# ---------------------------------------------------------------------------
# Software Catalog
# ---------------------------------------------------------------------------
with st.expander("Software Catalog", expanded=False):
    catalog_df = build_software_catalog(nodes, edges)
    render_software_catalog_explorer(catalog_df)

# ---------------------------------------------------------------------------
# Seed Data Preview
# ---------------------------------------------------------------------------
with st.expander("Seed Data Preview", expanded=False):
    tab_nodes, tab_edges, tab_graph = st.tabs(['Nodes', 'Edges', 'Graph View'])
    with tab_nodes:
        st.dataframe(nodes, width='stretch')
    with tab_edges:
        st.dataframe(edges, width='stretch')
    with tab_graph:
        render_graph_view(nodes, edges)
