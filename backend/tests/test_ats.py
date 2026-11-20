import pytest

from app.ats.score import analyse
from app.parsing.extract import UnsupportedFileError, extract
from app.parsing.sections import split_sections

from . import fixtures


def checks_by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_good_docx_scores_high():
    report = analyse(extract("cv.docx", fixtures.good_docx()))
    assert report["score"] >= 85, report["issues"]
    assert {"experience", "education", "skills", "projects"} <= set(report["sections_found"])
    assert report["bullet_count"] == 6


def test_bad_docx_flags_layout_and_content_problems():
    report = analyse(extract("cv.docx", fixtures.bad_docx()))
    c = checks_by_id(report)
    assert report["score"] < 60
    for check_id in ("tables", "columns", "header_footer", "core_sections",
                     "action_verbs", "quantified"):
        assert not c[check_id]["passed"], check_id
    # Most serious problems come first.
    assert report["issues"][0]["severity"] == "critical"


def test_good_pdf_matches_docx():
    report = analyse(extract("cv.pdf", fixtures.good_pdf()))
    c = checks_by_id(report)
    assert c["columns"]["passed"]
    assert c["contact"]["passed"]
    assert report["score"] >= 80, report["issues"]


def test_two_column_pdf_detected():
    doc = extract("cv.pdf", fixtures.two_column_pdf())
    assert doc.multi_column


def test_scores_are_deterministic():
    data = fixtures.good_docx()
    assert analyse(extract("a.docx", data)) == analyse(extract("a.docx", data))


def test_year_range_is_not_a_phone_number():
    from app.ats.checks import has_phone

    assert not has_phone("B.Tech, 2022 - 2026")
    assert has_phone("+353 87 123 4567")


def test_heading_aliases():
    r = split_sections(["Jane", "Work Experience", "did stuff", "Technical Skills:", "Python"])
    assert r.sections["experience"] == ["did stuff"]
    assert r.sections["skills"] == ["Python"]
    assert r.header == ["Jane"]


def test_rejects_other_file_types():
    with pytest.raises(UnsupportedFileError):
        extract("cv.txt", b"hello")


def test_cid_bullets_are_treated_as_bullets():
    from app.parsing.extract import _fix_cid

    fixed = _fix_cid("(cid:127) Designed a scoring engine for 500 products\nNode(cid:3).js")
    assert fixed.splitlines() == ["• Designed a scoring engine for 500 products", "Node.js"]

    from app.ats.checks import Context, check_action_verbs, check_special_chars, find_bullets
    from app.parsing.extract import ExtractedDocument

    text = "EXPERIENCE\n" + "\n".join(
        f"(cid:127) Built feature number {i} for the dashboard team" for i in range(4))
    doc = ExtractedDocument(file_type="pdf", text=_fix_cid(text),
                            lines=_fix_cid(text).splitlines(), undecodable_glyphs=4)
    resume = split_sections(doc.lines)
    ctx = Context(doc=doc, resume=resume, bullets=find_bullets(resume))
    assert len(ctx.bullets) == 4
    assert check_action_verbs(ctx).score == 1.0
    assert check_special_chars(ctx).severity == "tip"
