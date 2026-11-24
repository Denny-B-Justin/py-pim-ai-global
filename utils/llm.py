"""LLM calls through the Posit mAI Gateway. No API keys: the gateway trusts the Connect app id."""
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

import requests

from constants import LLM_TIMEOUT_S, MAI_BASE_URL, MAI_ENDPOINTS, MODEL_BY_ID
from utils.security import require_https

log = logging.getLogger("pim.llm")


class LLMError(Exception):
    """`str(exc)` is safe to show to users; `detail` is for logs only."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


def _gateway() -> str:
    if not MAI_BASE_URL:
        raise LLMError("The AI gateway is not configured. Please contact the administrator.", "MAI_BASE_URL unset")
    return require_https(MAI_BASE_URL if MAI_BASE_URL.endswith("/") else MAI_BASE_URL + "/", "MAI_BASE_URL")


def _endpoint(provider: str) -> str:
    value = MAI_ENDPOINTS.get(provider, "")
    if not value:
        raise LLMError("This model is not configured. Please pick another model.", f"MAI_ENDPOINT_{provider.upper()} unset")
    return value


def _headers() -> dict:
    app_id = os.environ.get("CONNECT_CONTENT_GUID")
    if not app_id:
        raise LLMError(
            "The AI gateway only accepts requests from the app running on Posit Connect.", "CONNECT_CONTENT_GUID unset"
        )
    return {"X-Posit-App-Id": app_id, "Content-Type": "application/json", "x-source-type": "interactive"}


def friendly_error(detail: str) -> str:
    m = detail.lower()
    rules = (
        (("overloaded",), "The AI model is temporarily overloaded. Please try again in a few seconds, or switch to a different model."),
        (("429", "rate limit", "rate_limit", "throttl"), "API rate limit reached. Please wait a moment and try again."),
        (("model not allowed",), "This model is not enabled on the AI gateway. Please pick another model."),
        (("access denied", "forbidden", "403", "invalid app"), "The AI gateway rejected the request. Please contact the administrator."),
        (("context_length", "maximum context", "too long"), "The query and context are too long for this model. Try a shorter question or a different model."),
        (("timeout", "timed out", "connection"), "The request timed out. Please try again."),
        (("content_filter", "safety", "blocked"), "The provider declined to answer due to its content policy. Try rephrasing the question."),
    )
    for needles, message in rules:
        if any(n in m for n in needles):
            return message
    return "An unexpected error occurred with the AI model. Please try again or switch to a different model."


def _is_bad_request(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) in (400, 422)


# ── Providers ────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    return OpenAI(
        base_url=_gateway(),
        api_key="not-used",
        default_headers=_headers(),
        default_query={"mai-endpoint": _endpoint("openai")},
        timeout=LLM_TIMEOUT_S,
        max_retries=1,
    )


def _openai(model: str, system: str, user: str, max_tokens: int, inline: bool) -> LLMResult:
    kwargs = {"input": f"{system}\n\n{user}"} if inline else {"input": user, "instructions": system}
    resp = _openai_client().responses.create(model=model, max_output_tokens=max_tokens, **kwargs)
    usage = getattr(resp, "usage", None)
    return LLMResult(resp.output_text or "", model, "openai", getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key="not-used",
        http_options=types.HttpOptions(base_url=_gateway().rstrip("/"), headers=_headers(), timeout=LLM_TIMEOUT_S * 1000),
    )


def _gemini(model: str, system: str, user: str, max_tokens: int, inline: bool) -> LLMResult:
    kwargs = {"input": f"{system}\n\n{user}"} if inline else {"input": user, "system_instruction": system}
    it = _gemini_client().interactions.create(
        model=model,
        generation_config={"max_output_tokens": max_tokens},
        extra_query={"mai-endpoint": _endpoint("gemini")},
        extra_headers=_headers(),
        **kwargs,
    )
    text = it.output_text or "".join(
        c.text for s in (getattr(it, "steps", None) or []) for c in (getattr(s, "content", None) or []) if getattr(c, "text", None)
    )
    usage = getattr(it, "usage", None)
    return LLMResult(text, model, "gemini", getattr(usage, "total_input_tokens", 0) or 0, getattr(usage, "total_output_tokens", 0) or 0)


class _HTTPStatus(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"HTTP {status_code}: {body[:200]}")
        self.status_code = status_code


def _claude(model: str, system: str, user: str, max_tokens: int, inline: bool) -> LLMResult:
    body = {
        "messages": [{"role": "user", "content": [{"text": f"{system}\n\n{user}" if inline else user}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if not inline:
        body["system"] = [{"text": system}]
    resp = requests.post(
        _gateway() + "converse",
        params={"mai-endpoint": _endpoint("claude")},
        headers=_headers(),
        json=body,
        timeout=LLM_TIMEOUT_S,
    )
    if resp.status_code >= 400:
        raise _HTTPStatus(resp.status_code, resp.text)
    data = resp.json()
    blocks = data.get("output", {}).get("message", {}).get("content", [])
    usage = data.get("usage", {})
    return LLMResult("".join(b.get("text", "") for b in blocks), model, "claude", usage.get("inputTokens", 0), usage.get("outputTokens", 0))


_PROVIDERS = {"openai": _openai, "gemini": _gemini, "claude": _claude}


def generate_answer(model_id: str, system: str, user: str, max_tokens: int) -> LLMResult:
    model = MODEL_BY_ID.get(model_id)
    if model is None:
        raise LLMError("Invalid model.", model_id)
    call = _PROVIDERS[model.provider]
    try:
        try:
            result = call(model.id, system, user, max_tokens, False)
        except Exception as exc:
            if not _is_bad_request(exc):
                raise
            log.warning("%s rejected system field (%s); retrying inline", model.provider, getattr(exc, "status_code", ""))
            result = call(model.id, system, user, max_tokens, True)
    except LLMError:
        raise
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log.warning("llm call failed model=%s %s", model.id, detail[:300])
        raise LLMError(friendly_error(detail), detail) from exc
    if not result.text.strip():
        raise LLMError("The model returned an empty answer. Please try again or switch to a different model.", "empty")
    result.model = model.label
    return result
