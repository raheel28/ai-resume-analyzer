from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from app.metrics import metrics_path


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return s[k]


def summarise(events: list[dict]) -> dict:
    ok = [e for e in events if e.get("ok")]
    times = [e["total_seconds"] for e in ok]
    proposed = sum(e.get("rewrites_proposed", 0) for e in ok)
    rejected = sum(e.get("rewrites_rejected", 0) for e in ok)
    by_reason: Counter = Counter()
    for e in ok:
        by_reason.update(e.get("rejected_by", {}))
    return {
        "requests": len(events),
        "success_rate": len(ok) / len(events) if events else None,
        "latency_median_s": statistics.median(times) if times else None,
        "latency_p90_s": percentile(times, 90) if times else None,
        "fallback_rate": sum(e.get("fallback_used", False) for e in events) / len(events) if events else None,
        "retried_rate": sum(e.get("attempts", 0) > 1 for e in events) / len(events) if events else None,
        "answered_by": dict(Counter(e.get("model") for e in ok)),
        "error_codes": dict(Counter(c for e in events for c in e.get("error_codes", []))),
        "rewrites_proposed": proposed,
        "rewrites_rejected_by_guard": rejected,
        "guard_rejection_rate": rejected / proposed if proposed else None,
        "rejected_by": dict(by_reason.most_common()),
    }


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else metrics_path()
    if not path.exists():
        print(f"No metrics yet at {path}. Run some AI reviews first.")
        return
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    r = summarise(events)
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    sec = lambda x: "n/a" if x is None else f"{x:.1f}s"
    print(f"AI usage from {path} ({r['requests']} requests)")
    print(f"  Success rate:            {pct(r['success_rate'])}")
    print(f"  Latency median / p90:    {sec(r['latency_median_s'])} / {sec(r['latency_p90_s'])}")
    print(f"  Needed a retry:          {pct(r['retried_rate'])}")
    print(f"  Fell back to backup model: {pct(r['fallback_rate'])}")
    print(f"  Answered by:             {r['answered_by']}")
    if r["error_codes"]:
        print(f"  Provider errors seen:    {r['error_codes']}")
    print(f"  AI rewrites proposed:    {r['rewrites_proposed']}")
    print(f"  Rejected by guard:       {r['rewrites_rejected_by_guard']} ({pct(r['guard_rejection_rate'])})")
    for reason, n in r["rejected_by"].items():
        print(f"    {reason:<36} {n}")


if __name__ == "__main__":
    main()
