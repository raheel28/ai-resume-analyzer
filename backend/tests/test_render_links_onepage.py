import io

import pdfplumber
from docx import Document
from docx.oxml.ns import qn

from app.edit.apply import Change, apply_to_lines
from app.edit.render import LAYOUTS, build_model, fit_one_page, link_segments, render_docx, render_pdf
from app.parsing.extract import extract

from . import fixtures


def test_pdf_links_are_extracted_with_anchor_text():
    doc = extract("cv.pdf", fixtures.dense_pdf_with_links())
    assert {"text": "GitHub", "url": "https://github.com/alexm"} in doc.links
    assert {"text": "LinkedIn", "url": "https://linkedin.com/in/alexm"} in doc.links


def test_link_segments_anchor_email_and_bare_urls():
    segs = link_segments("a@b.com | GitHub | linkedin.com/in/x | https://x.dev/p.",
                         [{"text": "GitHub", "url": "https://github.com/u"}])
    links = {t: u for t, u in segs if u}
    assert links == {"a@b.com": "mailto:a@b.com", "GitHub": "https://github.com/u",
                     "linkedin.com/in/x": "https://linkedin.com/in/x", "https://x.dev/p": "https://x.dev/p"}


def _pdf_links(data):
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return len(pdf.pages), {h["uri"] for p in pdf.pages for h in p.hyperlinks}, pdf.pages[0].extract_text()


def test_rebuilt_pdf_is_one_page_and_keeps_links():
    doc = extract("cv.pdf", fixtures.dense_pdf_with_links())
    model = build_model(doc.lines, doc.links)
    layout, pages = fit_one_page(model)
    assert pages == 1
    n, uris, text = _pdf_links(render_pdf(model, layout))
    assert n == 1
    assert {"https://github.com/alexm", "https://linkedin.com/in/alexm",
            "mailto:alex.murphy@example.com"} <= uris
    assert "(cid:" not in text


def test_rebuilt_docx_keeps_links():
    doc = extract("cv.pdf", fixtures.dense_pdf_with_links())
    model = build_model(doc.lines, doc.links)
    out = Document(io.BytesIO(render_docx(model)))
    targets = {r.target_ref for r in out.part.rels.values() if r.is_external}
    assert {"https://github.com/alexm", "https://linkedin.com/in/alexm",
            "mailto:alex.murphy@example.com"} <= targets
    # and the anchor words are still in the text
    assert "GitHub" in "".join(t.text for t in out.element.body.iter(qn("w:t")))


def test_docx_links_round_trip():
    doc = extract("cv.pdf", fixtures.dense_pdf_with_links())
    again = extract("out.docx", render_docx(build_model(doc.lines, doc.links)))
    assert {"text": "GitHub", "url": "https://github.com/alexm"} in again.links


def test_too_long_resume_reports_pages_instead_of_cutting():
    doc = extract("cv.pdf", fixtures.dense_pdf_with_links())
    lines = doc.lines + [f"• Extra accomplishment number {i} described in quite a lot of detail here"
                         for i in range(80)]
    model = build_model(lines, doc.links)
    layout, pages = fit_one_page(model)
    assert layout == LAYOUTS[-1] and pages >= 2


def test_clipped_anchor_text_snaps_to_whole_words():
    """Real PDFs: link boxes clip the first letter and include the separator."""
    links = [{"text": "itHub", "url": "https://github.com/u"},
             {"text": "eetCode", "url": "https://leetcode.com/u/x/"},
             {"text": "aheel@gmail.com", "url": "mailto:raheel@gmail.com"}]
    segs = link_segments("raheel@gmail.com | LeetCode | GitHub | LinkedIn", links)
    linked = {t: u for t, u in segs if u}
    assert linked == {"raheel@gmail.com": "mailto:raheel@gmail.com",
                      "LeetCode": "https://leetcode.com/u/x/", "GitHub": "https://github.com/u"}


def test_each_original_link_used_once():
    used = set()
    links = [{"text": "GitHub", "url": "https://github.com/u"}]
    first = link_segments("GitHub | LinkedIn", links, used)
    later = link_segments("Tools: Git, GitHub, Postman", links, used)
    assert ("GitHub", "https://github.com/u") in first
    assert all(u is None for _, u in later)
