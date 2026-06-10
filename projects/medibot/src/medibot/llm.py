"""Cloud-hosted LLM inference via the Groq API."""

import os

from groq import Groq

from medibot.config import LLM_MODEL


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        try:  # Streamlit Cloud stores secrets in st.secrets
            import streamlit as st

            key = st.secrets.get("GROQ_API_KEY", "")
        except Exception:
            pass
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Export it or add it to .streamlit/secrets.toml."
        )
    return key


_client: Groq | None = None


def complete(system: str, user: str, temperature: float = 0.1) -> str:
    global _client
    if _client is None:
        _client = Groq(api_key=_api_key())
    response = _client.chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content.strip()
