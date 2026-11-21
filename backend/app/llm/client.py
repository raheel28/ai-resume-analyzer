"""Provider-agnostic LLM wrapper.

Everything else in the app calls `get_client().generate(system, prompt, Model)`
and gets back a validated Pydantic object. Switching from Gemini to Claude,
OpenAI or Grok means adding one class here.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("uvicorn.error")  # shows up in the run.sh terminal


class LLMError(RuntimeError):
    """The provider failed or returned something unusable."""


class LLMNotConfigured(LLMError):
    """No API key / provider set up."""


class LLMClient(Protocol):
    last_model: str | None

    def generate(self, system: str, prompt: str, schema: type[T]) -> T: ...


# Errors worth retrying or moving to another model for.
RETRYABLE = {408, 429, 500, 502, 503, 504}
MODEL_MISSING = {404}


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    text = str(exc)
    for c in RETRYABLE | MODEL_MISSING:
        if text.startswith(str(c)) or f" {c} " in text:
            return c
    if "timed out" in text.lower() or "timeout" in text.lower():
        return 408
    return None


class GeminiClient:
    def __init__(self, api_key: str, models: list[str], timeout_s: float = 25,
                 retries: int = 1, sleep: Callable[[float], None] = time.sleep):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMNotConfigured("Install the SDK: pip install google-genai") from exc
        try:
            self._client = genai.Client(
                api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        except TypeError:  # older SDKs without HttpOptions(timeout=...)
            self._client = genai.Client(api_key=api_key)
        self._models = models
        self._retries = retries
        self._sleep = sleep
        self.last_model: str | None = None
        self.last_attempts: list[dict] = []  # per-call record for usage metrics

    def _call(self, model: str, system: str, prompt: str, schema: type[T]) -> str | None:
        from google.genai import types

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,  # SDK accepts Pydantic models directly
                temperature=0.2,
            ),
        )
        return response.text

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        last_error: Exception | None = None
        self.last_attempts = []
        for i, model in enumerate(self._models):
            # Retry the primary model on "busy" errors; fallbacks get one try each.
            attempts = 1 + (self._retries if i == 0 else 0)
            for attempt in range(attempts):
                started = time.monotonic()
                try:
                    text = self._call(model, system, prompt, schema)
                    elapsed = time.monotonic() - started
                    log.info("AI review: %s answered in %.1fs", model, elapsed)
                    self.last_attempts.append({"model": model, "ok": True, "seconds": round(elapsed, 2)})
                    self.last_model = model
                    return _parse(schema, text)
                except LLMError:
                    raise
                except Exception as exc:  # SDK raises its own APIError types
                    code = _status_code(exc)
                    self.last_attempts.append({"model": model, "ok": False, "code": code,
                                               "seconds": round(time.monotonic() - started, 2)})
                    log.warning("AI review: %s failed after %.1fs (%s): %s", model,
                                time.monotonic() - started, code, str(exc)[:160])
                    last_error = exc
                    if code in MODEL_MISSING or code in (408, 504):
                        # Model unavailable, or so slow it timed out (our timeout,
                        # or Gemini's own 504 DEADLINE_EXCEEDED): retrying the same
                        # model would just double the wait. Use the next one.
                        break
                    if code not in RETRYABLE:
                        raise LLMError(f"Gemini request failed: {exc}") from exc
                    if attempt + 1 < attempts:
                        self._sleep(2 * (attempt + 1))
        raise LLMError(
            "All models are busy or unavailable right now "
            f"(tried {', '.join(self._models)}). Please try again in a minute."
        ) from last_error


class FakeClient:
    """For tests and offline development: returns whatever `responder` builds."""

    def __init__(self, responder: Callable[[str, str], str]):
        self._responder = responder
        self.calls: list[tuple[str, str]] = []
        self.last_model: str | None = "fake"
        self.last_attempts: list[dict] = []

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        self.calls.append((system, prompt))
        return _parse(schema, self._responder(system, prompt))


def _parse(schema: type[T], text: str | None) -> T:
    if not text:
        raise LLMError("Empty response from model")
    try:
        return schema.model_validate_json(text)
    except Exception as exc:
        raise LLMError(f"Model returned invalid JSON for {schema.__name__}") from exc


def get_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "gemini")
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key or key == "your-key-here":
            raise LLMNotConfigured("Set GEMINI_API_KEY in backend/.env to enable the AI review")
        primary = os.getenv("LLM_MODEL", "gemini-3.8-flash")
        fallbacks = [m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()]
        models = [primary] + [m for m in fallbacks if m != primary]
        return GeminiClient(key, models, timeout_s=float(os.getenv("LLM_TIMEOUT_S", "25")))
    raise LLMNotConfigured(f"Unknown LLM_PROVIDER: {provider}")
