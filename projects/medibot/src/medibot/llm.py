"""Cloud-hosted LLM inference via the OpenAI API."""

from contextvars import ContextVar
import os

from openai import OpenAI

from medibot.config import LLM_MODEL

_TOKEN_USAGE: ContextVar[dict | None] = ContextVar("token_usage", default=None)


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


def reset_token_usage() -> None:
    _TOKEN_USAGE.set(
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": [],
        }
    )


def get_token_usage() -> dict:
    usage = _TOKEN_USAGE.get()
    if not usage:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": [],
        }
    return {
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "calls": [dict(call) for call in usage["calls"]],
    }


def _record_usage(response, model: str) -> None:
    usage = _TOKEN_USAGE.get()
    response_usage = getattr(response, "usage", None)
    if usage is None or response_usage is None:
        return

    prompt_tokens = response_usage.prompt_tokens or 0
    completion_tokens = response_usage.completion_tokens or 0
    total_tokens = response_usage.total_tokens or prompt_tokens + completion_tokens

    usage["prompt_tokens"] += prompt_tokens
    usage["completion_tokens"] += completion_tokens
    usage["total_tokens"] += total_tokens
    usage["calls"].append(
        {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
    )
    _TOKEN_USAGE.set(usage)


def complete(system: str, user: str, temperature: float = 0.1) -> str:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_api_key())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model = _model()
    used_model = model
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
            used_model = LLM_MODEL
            response = _client.chat.completions.create(
                model=LLM_MODEL,
                temperature=temperature,
                messages=messages,
            )
        else:
            raise
    _record_usage(response, used_model)
    return response.choices[0].message.content.strip()
