from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import sys
import os

# Add src to path so we can import hybrid_rag
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from hybrid_rag import run_hybrid_rag

ROOT = Path(__file__).resolve().parents[1]


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / 'graph' / name)


st.set_page_config(page_title='nexusgraph-ai', layout='wide')
st.title('nexusgraph-ai')
st.caption('GraphRAG for Organizational Knowledge and Decision Intelligence')

nodes = load_csv('nodes.csv')
edges = load_csv('edges.csv')
queries = json.loads((ROOT / 'evaluation' / 'comparison_queries.json').read_text())

metric_cols = st.columns(3)
metric_cols[0].metric('Nodes', len(nodes))
metric_cols[1].metric('Relationships', len(edges))
metric_cols[2].metric('Comparison Queries', len(queries))

st.subheader('Graph Shape')
left, right = st.columns(2)
with left:
    st.dataframe(nodes['label'].value_counts().rename_axis('node_type').reset_index(name='count'), use_container_width=True)
with right:
    st.dataframe(edges['relationship'].value_counts().rename_axis('relationship').reset_index(name='count'), use_container_width=True)

st.subheader('Required GraphRAG vs Vector RAG Queries')
query = st.selectbox('Sample Queries', [item['query'] for item in queries])
selected = next(item for item in queries if item['query'] == query)
st.write(f"**Insight:** {selected['why_graphrag_is_useful']}")

st.divider()

st.subheader('Ask NexusGraph')
user_query = st.text_input("Enter your question about organizational knowledge:", placeholder="e.g., How is Emma Chen related to the playback service?")

if st.button("Run Hybrid RAG"):
    if user_query:
        with st.spinner("Analyzing graph and vector data..."):
            try:
                # We use the raw stream to show progress if needed, but for now just the answer
                answer = run_hybrid_rag(user_query)
                st.write("**Answer:**")
                st.write(answer)
            except Exception as e:
                st.error(f"Error running RAG: {str(e)}")
    else:
        st.warning("Please enter a query first.")

st.divider()

st.subheader('Seed Data Preview')
tab_nodes, tab_edges = st.tabs(['Nodes', 'Edges'])
with tab_nodes:
    st.dataframe(nodes, use_container_width=True)
with tab_edges:
    st.dataframe(edges, use_container_width=True)
