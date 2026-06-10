"""MediBot — Streamlit app: login, role-scoped chat, citations, RBAC messaging.

Run locally:
    streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from medibot.chat import chat
from medibot.config import (
    CHUNKS_PATH,
    DEMO_USERS,
    ROLE_COLLECTIONS,
    ROLE_LABELS,
    SQL_RAG_ROLES,
)

st.set_page_config(page_title="MediBot — MediAssist Health Network", page_icon="🏥", layout="wide")


@st.cache_resource(show_spinner="Loading hybrid index + models (first run only)...")
def get_retriever():
    from medibot.index import build_index
    from medibot.retrieval import HybridRetriever

    if not CHUNKS_PATH.exists():
        st.error(
            "chunks.json not found. Run the ingestion pipeline first:\n\n"
            "`PYTHONPATH=src python -m medibot.ingest`"
        )
        st.stop()
    client = build_index()
    return HybridRetriever(client)


def login_screen():
    st.title("🏥 MediBot")
    st.caption("MediAssist Health Network — internal knowledge assistant")
    left, right = st.columns([1, 1])

    with left:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            record = DEMO_USERS.get(username.strip())
            if record and record[0] == password:
                st.session_state.user = {
                    "username": username.strip(),
                    "role": record[1],
                    "name": record[2],
                }
                st.session_state.messages = []
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with right:
        st.subheader("Demo accounts")
        st.table(
            [
                {"Username": u, "Password": p, "Role": role}
                for u, (p, role, _) in DEMO_USERS.items()
            ]
        )


def sidebar(user: dict):
    role = user["role"]
    with st.sidebar:
        st.markdown(f"### {ROLE_LABELS[role]}")
        st.markdown(f"**{user['name']}**  \n`{user['username']}`")
        st.divider()
        st.markdown("**Accessible collections**")
        for coll in ROLE_COLLECTIONS[role]:
            st.markdown(f"- 🗂️ `{coll}`")
        if role in SQL_RAG_ROLES:
            st.markdown("- 📊 `analytics database (SQL RAG)`")
        st.divider()
        if st.button("Log out", use_container_width=True):
            st.session_state.clear()
            st.rerun()


RETRIEVAL_BADGES = {
    "hybrid_rag": "🔀 Hybrid RAG",
    "sql_rag": "📊 SQL RAG",
    "blocked": "⛔ Blocked by RBAC",
}


def render_response(msg: dict):
    st.markdown(msg["content"])
    badge = RETRIEVAL_BADGES.get(msg.get("retrieval_type", ""), "")
    if badge:
        st.caption(badge)
    if msg.get("sql"):
        with st.expander("Generated SQL"):
            st.code(msg["sql"], language="sql")
    if msg.get("sources"):
        with st.expander(f"📚 Sources ({len(msg['sources'])})"):
            for i, src in enumerate(msg["sources"], 1):
                score = (
                    f" · rerank score {msg['rerank_scores'][i-1]:.3f}"
                    if msg.get("rerank_scores")
                    else ""
                )
                st.markdown(
                    f"**[{i}] {src['source_document']}** — "
                    f"{src['section_title'] or 'untitled section'} "
                    f"(`{src['collection']}`){score}"
                )


def chat_screen(user: dict):
    role = user["role"]
    st.title("🏥 MediBot")
    st.caption(
        f"Signed in as **{user['name']}** · {ROLE_LABELS[role]} · "
        f"access: {', '.join(ROLE_COLLECTIONS[role])}"
    )
    retriever = get_retriever()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role_ui"]):
            if msg["role_ui"] == "assistant":
                render_response(msg)
            else:
                st.markdown(msg["content"])

    if question := st.chat_input("Ask MediBot..."):
        st.session_state.messages.append({"role_ui": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Retrieving and thinking..."):
                try:
                    response = chat(question, role, retriever)
                    msg = {
                        "role_ui": "assistant",
                        "content": response.answer,
                        "sources": response.sources,
                        "retrieval_type": response.retrieval_type,
                        "sql": response.sql,
                        "rerank_scores": response.rerank_scores,
                    }
                except Exception as exc:
                    msg = {
                        "role_ui": "assistant",
                        "content": f"Something went wrong: `{exc}`",
                        "retrieval_type": "",
                    }
            render_response(msg)
        st.session_state.messages.append(msg)


if "user" not in st.session_state:
    login_screen()
else:
    chat_screen(st.session_state.user)
