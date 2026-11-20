"""Privacy-safe usage metrics: one JSON line per AI request.

Records timings, which model answered, retries/fallbacks and how many AI
rewrites the guard accepted or rejected (and why). Never records resume or
job-description text. Summarise with:  python -m evals.usage_report
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger("uvicorn.error")
_lock = threading.Lock()


def metrics_path() -> Path:
    return Path(os.getenv("METRICS_PATH", Path(__file__).resolve().parent.parent / "data" / "metrics.jsonl"))


def reason_category(reason: str) -> str:
    """'invented quantity: doubled' -> 'invented quantity'."""
    return reason.split(":", 1)[0].strip() if reason else "unknown"


def record(event: dict) -> None:
    if os.getenv("METRICS_DISABLED"):
        return
    event = {"ts": round(time.time()), **event}
    try:
        path = metrics_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as exc:  # metrics must never break a request
        log.warning("Could not write metrics: %s", exc)


def ai_event(endpoint: str, client, started: float, result: dict | None = None,
             error: str | None = None) -> dict:
    attempts = getattr(client, "last_attempts", []) or []
    event = {
        "endpoint": endpoint,
        "ok": error is None,
        "total_seconds": round(time.monotonic() - started, 2),
        "model": getattr(client, "last_model", None) if error is None else None,
        "attempts": len(attempts),
        "models_tried": [a["model"] for a in attempts],
        "fallback_used": len({a["model"] for a in attempts}) > 1,
        "error_codes": [a.get("code") for a in attempts if not a["ok"]],
    }
    if error:
        event["error"] = error[:120]
    if result:
        rejected = result.get("rejected_rewrites", [])
        event.update({
            "ai_score": result.get("score"),
            "rewrites_proposed": len(result.get("rewrites", [])) + len(rejected),
            "rewrites_accepted": len(result.get("rewrites", [])),
            "rewrites_rejected": len(rejected),
            "rejected_by": _count(reason_category(r.get("reason", "")) for r in rejected),
            "placeholders": sum(1 for r in result.get("rewrites", []) if r.get("needs_input")),
        })
    return event


def _count(items) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out
