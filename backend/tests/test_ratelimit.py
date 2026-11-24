import pytest

from app.ratelimit import RateLimiter, client_ip, friendly_wait, parse_limit


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_parse_limit():
    assert parse_limit("10/hour") == (10, 3600)
    assert parse_limit("60 / minutes") == (60, 60)
    with pytest.raises(ValueError):
        parse_limit("10/fortnight")


def test_sliding_window_per_ip():
    clock = Clock()
    rl = RateLimiter("3/minute", clock=clock)
    assert [rl.check("a") for _ in range(3)] == [None, None, None]
    wait = rl.check("a")
    assert wait == pytest.approx(60)
    assert rl.check("b") is None
    clock.t += 30
    assert rl.check("a") == pytest.approx(30)
    clock.t += 31
    assert rl.check("a") is None


def test_memory_is_pruned():
    clock = Clock()
    rl = RateLimiter("1/second", clock=clock, max_keys=10)
    for i in range(10):
        rl.check(f"ip{i}")
    clock.t += 5
    rl.check("new")
    assert len(rl._hits) <= 2


def test_forwarded_for_only_trusted_behind_proxy(monkeypatch):
    headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert client_ip(headers, "10.0.0.1") == "10.0.0.1"
    monkeypatch.setenv("TRUST_PROXY", "1")
    assert client_ip(headers, "10.0.0.1") == "1.2.3.4"


def test_friendly_wait():
    assert friendly_wait(12.2) == "13 seconds"
    assert friendly_wait(1500) == "25 minutes"
    assert friendly_wait(7200) == "2 hours"
