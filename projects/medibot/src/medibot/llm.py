"""Cloud-hosted LLM inference via the OpenAI API."""

import os

from openai import OpenAI

from medibot.config import LLM_MODEL


def _api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        try:  # Streamlit Cloud stores secrets in st.secrets
            import streamlit as st

            key = st.secrets.get("OPENAI_API_KEY", "")
        except Exception:
            pass
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it or add it to .streamlit/secrets.toml."
        )
    return key


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", LLM_MODEL)


_client: OpenAI | None = None


def complete(system: str, user: str, temperature: float = 0.1) -> str:
    global _client
    _ = temperature  # Kept for the existing call sites; GPT-5.x uses defaults here.
    if _client is None:
        _client = OpenAI(api_key=_api_key())
    response = _client.responses.create(
        model=_model(),
        instructions=system,
        input=user,
        reasoning={"effort": "low"},
        text={"verbosity": "low"},
    )
    return response.output_text.strip()
