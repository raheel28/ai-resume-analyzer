import io

import pytest
from docx import Document

from app.edit.apply import Change, apply_to_lines, edit_docx_in_place, validate_changes
from app.edit.render import build_model, render_docx, render_pdf
from app.parsing.extract import extract, merge_wrapped_bullets

from . import fixtures

OLD = "Reduced API latency by 40% by adding Redis caching to the product search service"
NEW = "Cut product-search API latency 40% by introducing a Redis caching layer"


def test_validate_rejects_unfilled_placeholders():
    with pytest.raises(ValueError, match="placeholders"):
        validate_changes([{"original": "x", "replacement": "Grew users by [X%]"}])
    with pytest.raises(ValueError, match="placeholders"):
        validate_changes([{"original": "x", "replacement": "Served [number of monthly active users here]"}])
    assert validate_changes([]) == []
    assert validate_changes([{"original": "a", "replacement": "  b   c "}])[0].replacement == "b c"


def test_docx_in_place_keeps_other_text_and_reports_misses():
    out, result = edit_docx_in_place(fixtures.good_docx(), [
        Change(OLD, NEW), Change("A bullet that does not exist anywhere", "x")])
    texts = [p.text for p in Document(io.BytesIO(out)).paragraphs]
    assert "• " + NEW in texts
    assert not any(OLD in t for t in texts)
    assert texts[0] == "Jane Doe"
    assert len(result.applied) == 1 and len(result.not_found) == 1


def test_rebuild_from_pdf_to_docx_and_pdf():
    doc = extract("cv.pdf", fixtures.good_pdf())
    lines, result = apply_to_lines(doc.lines, [Change(OLD, NEW)])
    assert result.applied == [OLD]
    model = build_model(lines)
    assert model.name == "Jane Doe"
    assert [s.title for s in model.sections][:2] == ["Summary", "Experience"]

    rebuilt = extract("out.docx", render_docx(model))
    assert NEW in rebuilt.text and OLD not in rebuilt.text
    assert rebuilt.table_count == 0 and not rebuilt.multi_column

    pdf = extract("out.pdf", render_pdf(model))
    assert "Redis caching layer" in pdf.text
    assert pdf.undecodable_glyphs == 0


def test_rebuilt_resume_still_scores_well():
    from app.ats.score import analyse

    doc = extract("cv.pdf", fixtures.good_pdf())
    lines, _ = apply_to_lines(doc.lines, [Change(OLD, NEW)])
    report = analyse(extract("out.docx", render_docx(build_model(lines))))
    assert report["score"] >= 85, report["issues"]


def test_merge_wrapped_bullets():
    lines = [
        "EXPERIENCE",
        "Software Intern, Fonebox — Jan 2026 - Mar 2026",
        "• Optimised PostgreSQL queries with composite indexes, cutting",
        "report load time by 15%.",
        "• Built an Angular dashboard for order tracking",
        "Akhila Labs — May 2025 - Dec 2025",
    ]
    assert merge_wrapped_bullets(lines) == [
        "EXPERIENCE",
        "Software Intern, Fonebox — Jan 2026 - Mar 2026",
        "• Optimised PostgreSQL queries with composite indexes, cutting report load time by 15%.",
        "• Built an Angular dashboard for order tracking",
        "Akhila Labs — May 2025 - Dec 2025",
    ]


def test_wrapped_text_lines_rejoined():
    model = build_model(["Jane", "SKILLS", "Python, C++,", "Linux, Git", "SUMMARY", "Line one", "Line two"])
    skills, summary = model.sections
    assert [l.text for l in skills.lines] == ["Python, C++, Linux, Git"]
    assert [l.text for l in summary.lines] == ["Line one Line two"]
