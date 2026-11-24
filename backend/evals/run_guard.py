from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.ai.guard import check_rewrite

DATA = Path(__file__).parent / "data"


SETS = {"dev": "guard_cases.jsonl", "holdout": "guard_cases_holdout.jsonl"}


def load_cases(name: str = "dev") -> list[dict]:
    path = DATA / SETS[name]
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def evaluate(set_name: str = "dev") -> dict:
    resume = (DATA / "guard_resume.txt").read_text()
    cases = load_cases(set_name)
    tp = fp = tn = fn = 0
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    errors = []
    for c in cases:
        verdict = check_rewrite(c["original"], c["suggested"], resume)
        predicted_reject = not verdict.ok
        should_reject = c["expect"] == "reject"
        correct = predicted_reject == should_reject
        by_cat[c["category"]][0] += correct
        by_cat[c["category"]][1] += 1
        if should_reject and predicted_reject:
            tp += 1
        elif should_reject:
            fn += 1
        elif predicted_reject:
            fp += 1
        else:
            tn += 1
        if not correct:
            errors.append({**c, "guard_reason": verdict.reason or "accepted"})

    n_reject, n_accept = tp + fn, tn + fp
    return {
        "set": set_name,
        "cases": len(cases),
        "recall": tp / n_reject if n_reject else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "false_rejection_rate": fp / n_accept if n_accept else None,
        "accuracy": (tp + tn) / len(cases),
        "confusion": {"caught": tp, "missed": fn, "wrongly_blocked": fp, "correctly_allowed": tn},
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_cat.items())},
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-errors", action="store_true")
    ap.add_argument("--set", choices=SETS, default="dev",
                    help="dev: cases used while improving the guard; holdout: written beforehand, never tuned on")
    args = ap.parse_args()
    r = evaluate(args.set)
    if args.json:
        print(json.dumps({k: v for k, v in r.items() if k != "errors" or args.show_errors}, indent=2))
        return
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    print(f"Guard eval ({r['set']} set) on {r['cases']} labelled rewrites")
    print(f"  Invented facts caught (recall): {pct(r['recall'])}  "
          f"({r['confusion']['caught']}/{r['confusion']['caught'] + r['confusion']['missed']})")
    print(f"  Precision of rejections:        {pct(r['precision'])}")
    print(f"  Honest rewrites wrongly blocked: {pct(r['false_rejection_rate'])}  "
          f"({r['confusion']['wrongly_blocked']}/{r['confusion']['wrongly_blocked'] + r['confusion']['correctly_allowed']})")
    print("  By category:")
    for cat, score in r["by_category"].items():
        print(f"    {cat:<26} {score}")
    if args.show_errors and r["errors"]:
        print("  Errors:")
        for e in r["errors"]:
            print(f"    [{e['id']}] expected {e['expect']}, guard said: {e['guard_reason']}")
            print(f"        {e['suggested']}")


if __name__ == "__main__":
    main()
