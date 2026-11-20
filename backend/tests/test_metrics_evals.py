import json
import time

from app import metrics
from app.ai.review import review_resume
from app.llm.client import FakeClient
from evals.run_guard import evaluate as guard_eval
from evals.run_keywords import evaluate as keyword_eval
from evals.usage_report import summarise


def test_metrics_event_has_no_resume_text(tmp_path, monkeypatch):
    monkeypatch.setenv("METRICS_PATH", str(tmp_path / "m.jsonl"))
    monkeypatch.delenv("METRICS_DISABLED", raising=False)
    secret = "Jane Doe secret resume text 12345"
    payload = {"rubric": [{"criterion": "impact", "score": 6, "reason": "r"}], "strengths": [],
               "improvements": [], "rewrites": [
                   {"original": secret, "suggested": "Led a team on " + secret, "reason": "x"}]}
    client = FakeClient(lambda s, p: json.dumps(payload))
    started = time.monotonic()
    result = review_resume(client, secret + " more words", [secret])
    metrics.record(metrics.ai_event("ai-review", client, started, result))
    line = (tmp_path / "m.jsonl").read_text()
    assert "secret" not in line and "Jane" not in line
    event = json.loads(line)
    assert event["rewrites_rejected"] == 1
    assert event["rejected_by"] == {"invented leadership": 1}


def test_usage_summary():
    events = [
        {"ok": True, "total_seconds": 4, "model": "a", "attempts": 1, "fallback_used": False,
         "rewrites_proposed": 6, "rewrites_rejected": 1, "rejected_by": {"invented quantity": 1}},
        {"ok": True, "total_seconds": 10, "model": "b", "attempts": 3, "fallback_used": True,
         "error_codes": [503, 503], "rewrites_proposed": 4, "rewrites_rejected": 0},
        {"ok": False, "total_seconds": 30, "attempts": 3, "fallback_used": True, "error_codes": [503, 503, 503]},
    ]
    r = summarise(events)
    assert r["requests"] == 3 and round(r["success_rate"], 2) == 0.67
    assert r["guard_rejection_rate"] == 0.1 and r["error_codes"] == {503: 5}


def test_guard_eval_thresholds():
    """Fails CI if a change makes the guard worse on the held-out set."""
    holdout = guard_eval("holdout")
    assert holdout["recall"] >= 0.9
    assert holdout["false_rejection_rate"] <= 0.15
    dev = guard_eval("dev")
    assert dev["recall"] >= 0.95 and dev["false_rejection_rate"] <= 0.05


def test_keyword_eval_thresholds():
    r = keyword_eval()
    assert r["precision"] >= 0.9 and r["recall"] >= 0.9
