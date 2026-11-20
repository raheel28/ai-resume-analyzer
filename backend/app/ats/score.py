"""Combine checks into an overall ATS score with a per-category breakdown."""

from __future__ import annotations

from app.parsing.extract import ExtractedDocument
from app.parsing.sections import split_sections

from .checks import ALL_CHECKS, CheckResult, Context, find_bullets

CATEGORY_LABELS = {
    "parseability": "Can an ATS read it?",
    "structure": "Structure & sections",
    "content": "Bullet quality",
}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "tip": 2, "pass": 3}


def _weighted(results: list[CheckResult]) -> float:
    total = sum(r.weight for r in results)
    return round(100 * sum(r.score * r.weight for r in results) / total) if total else 0


def grade(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs work"
    return "Poor"


def analyse(doc: ExtractedDocument) -> dict:
    resume = split_sections(doc.lines)
    ctx = Context(doc=doc, resume=resume, bullets=find_bullets(resume))
    results = [check(ctx) for check in ALL_CHECKS]

    categories = []
    for key, label in CATEGORY_LABELS.items():
        group = [r for r in results if r.category == key]
        categories.append({"id": key, "label": label, "score": _weighted(group)})

    overall = _weighted(results)
    issues = sorted((r for r in results if not r.passed),
                    key=lambda r: (SEVERITY_ORDER[r.severity], -r.weight))

    return {
        "score": overall,
        "grade": grade(overall),
        "categories": categories,
        "issues": [r.to_dict() for r in issues],
        "checks": [r.to_dict() for r in results],
        "sections_found": sorted(k for k in resume.sections if not k.startswith("other:")),
        "bullet_count": len(ctx.bullets),
        "warnings": doc.warnings,
    }
