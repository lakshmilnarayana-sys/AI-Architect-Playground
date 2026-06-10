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
    model = os.environ.get("OPENAI_MODEL", "")
    if not model:
        try:
            import streamlit as st

            model = st.secrets.get("OPENAI_MODEL", "")
        except Exception:
            pass
    return model or LLM_MODEL


_client: OpenAI | None = None


def complete(system: str, user: str, temperature: float = 0.1) -> str:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_api_key())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model = _model()
    try:
        response = _client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
    except Exception as exc:
        error_text = str(exc)
        if model != LLM_MODEL and (
            "model_not_found" in error_text or "does not have access to model" in error_text
        ):
            response = _client.chat.completions.create(
                model=LLM_MODEL,
                temperature=temperature,
                messages=messages,
            )
        else:
            raise
    return response.choices[0].message.content.strip()
