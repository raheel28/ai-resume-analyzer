import pytest
from pydantic import BaseModel

from app.llm.client import GeminiClient, LLMError


class Out(BaseModel):
    ok: bool


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"{code} ERROR")
        self.code = code


def make_client(models, script):
    c = object.__new__(GeminiClient)
    c._models, c._retries, c._sleep, c.last_model = models, 1, lambda s: None, None
    c.calls = []

    def call(model, system, prompt, schema):
        c.calls.append(model)
        result = script[model].pop(0)
        if isinstance(result, int):
            raise FakeAPIError(result)
        return result

    c._call = call
    return c


def test_retries_busy_primary_then_succeeds():
    c = make_client(["a", "b"], {"a": [503, '{"ok": true}']})
    assert c.generate("s", "p", Out).ok
    assert c.calls == ["a", "a"] and c.last_model == "a"


def test_falls_back_when_primary_stays_busy():
    c = make_client(["a", "b"], {"a": [503, 503], "b": ['{"ok": true}']})
    assert c.generate("s", "p", Out).ok
    assert c.calls == ["a", "a", "b"] and c.last_model == "b"


def test_missing_model_skips_straight_to_fallback():
    c = make_client(["old", "b"], {"old": [404], "b": ['{"ok": true}']})
    assert c.generate("s", "p", Out).ok
    assert c.calls == ["old", "b"]


def test_bad_request_is_not_retried():
    c = make_client(["a", "b"], {"a": [400]})
    with pytest.raises(LLMError, match="request failed"):
        c.generate("s", "p", Out)
    assert c.calls == ["a"]


def test_all_busy_gives_friendly_error():
    c = make_client(["a", "b"], {"a": [503, 429], "b": [503]})
    with pytest.raises(LLMError, match="busy or unavailable"):
        c.generate("s", "p", Out)


def test_timeout_moves_to_next_model_without_retrying():
    c = make_client(["slow", "b"], {"slow": [408], "b": ['{"ok": true}']})
    assert c.generate("s", "p", Out).ok
    assert c.calls == ["slow", "b"]


def test_deadline_exceeded_moves_on_instead_of_retrying():
    c = make_client(["slow", "b"], {"slow": [504], "b": ['{"ok": true}']})
    assert c.generate("s", "p", Out).ok
    assert c.calls == ["slow", "b"]
