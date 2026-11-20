"""Evaluate rule-based skill extraction from job descriptions on hand-labelled ads.

  precision = extracted skills that are really asked for / all extracted
  recall    = asked-for skills extracted / all asked-for skills
  importance accuracy = required vs nice-to-have correct, on correctly found skills

Usage (from backend/):  python -m evals.run_keywords [--show-errors]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.jd.match import classify

DATA = Path(__file__).parent / "data"


def evaluate() -> dict:
    cases = [json.loads(l) for l in (DATA / "jd_cases.jsonl").read_text().splitlines() if l]
    tp = fp = fn = imp_ok = 0
    errors = []
    for c in cases:
        got = classify(c["jd"])
        want = set(c["skills"])
        found = set(got)
        tp += len(found & want)
        fp += len(found - want)
        fn += len(want - found)
        for s in found & want:
            expected = "nice" if s in c["nice"] else "required"
            imp_ok += got[s] == expected
            if got[s] != expected:
                errors.append(f"[{c['id']}] {s}: importance {got[s]}, expected {expected}")
        errors += [f"[{c['id']}] extra: {s}" for s in sorted(found - want)]
        errors += [f"[{c['id']}] missed: {s}" for s in sorted(want - found)]
    return {
        "ads": len(cases),
        "labelled_skills": tp + fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "importance_accuracy": imp_ok / tp if tp else None,
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-errors", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = evaluate()
    if args.json:
        print(json.dumps(r if args.show_errors else {k: v for k, v in r.items() if k != "errors"}, indent=2))
        return
    print(f"Keyword extraction eval on {r['ads']} job ads ({r['labelled_skills']} labelled skills)")
    print(f"  Precision:            {r['precision']:.0%}")
    print(f"  Recall:               {r['recall']:.0%}")
    print(f"  Required vs nice:     {r['importance_accuracy']:.0%} correct")
    if args.show_errors:
        print("  Errors:")
        for e in r["errors"]:
            print("    " + e)


if __name__ == "__main__":
    main()
