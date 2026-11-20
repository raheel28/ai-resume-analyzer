"""Rebuild a resume as a clean, single-column, ATS-friendly DOCX or PDF.

No tables, columns, text boxes, icons or header/footer content: just a name,
a contact line, standard section headings and real bullet points.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from app.parsing.sections import split_sections

from .apply import LITERAL_BULLET_RE

STANDARD_TITLES = {
    "summary": "Summary", "experience": "Experience", "projects": "Projects",
    "education": "Education", "skills": "Skills", "certifications": "Certifications",
    "achievements": "Achievements", "publications": "Publications",
    "volunteering": "Leadership & Activities", "languages": "Languages", "interests": "Interests",
}
# Sections where non-bullet lines are usually "Role, Company — dates" titles.
TITLED_SECTIONS = {"experience", "projects", "education", "volunteering"}
ICON_RE = re.compile(r"[-]")


@dataclass
class Line:
    text: str
    kind: str  # "bullet" | "title" | "text"


@dataclass
class Section:
    title: str
    lines: list[Line] = field(default_factory=list)


@dataclass
class ResumeModel:
    name: str
    contact: list[str]
    sections: list[Section]
    links: list[dict] = field(default_factory=list)  # [{"text", "url"}] from the original file


def build_model(lines: list[str], links: list[dict] | None = None) -> ResumeModel:
    lines = [ICON_RE.sub("", ln).strip() for ln in lines]
    parsed = split_sections([ln for ln in lines if ln])
    header = parsed.header or ["Your Name"]

    sections = []
    for key, body in parsed.sections.items():
        if not body:
            continue
        title = STANDARD_TITLES.get(key) or parsed.titles.get(key, key).title()
        section = Section(title)
        for ln in body:
            m = LITERAL_BULLET_RE.match(ln)
            if m:
                section.lines.append(Line(ln[m.end():].strip(), "bullet"))
            elif key in TITLED_SECTIONS and len(ln.split()) <= 20:
                section.lines.append(Line(ln, "title"))
            else:
                prev = section.lines[-1] if section.lines else None
                # Re-join plain text that the PDF wrapped onto several lines
                # (a summary paragraph, a long skills list).
                if prev and prev.kind == "text" and (
                        key == "summary" or prev.text.rstrip().endswith((",", "/", "&"))
                        or ln[:1].islower()):
                    prev.text = f"{prev.text} {ln}"
                else:
                    section.lines.append(Line(ln, "text"))
        sections.append(section)

    return ResumeModel(name=header[0], contact=header[1:], sections=sections, links=links or [])


# ------------------------------------------------------------------ links

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s|,;]+"
    r"|\b(?:linkedin\.com|github\.com|gitlab\.com|leetcode\.com|kaggle\.com|medium\.com|"
    r"behance\.net|dribbble\.com|[\w-]+\.(?:dev|io|me|vercel\.app|netlify\.app|github\.io))"
    r"(?:/[^\s|,;]*)?",
    re.I,
)


def _normalise_url(raw: str) -> str:
    url = raw.rstrip(".)")
    return url if re.match(r"https?://", url, re.I) else "https://" + url


_WORD_CHARS = re.compile(r"[\w.@+\-/]")


def _snap_to_word(text: str, a: int, b: int) -> tuple[int, int]:
    """Grow [a, b) to whole words ("itHub" -> "GitHub") without swallowing
    separators or trailing punctuation."""
    while a > 0 and _WORD_CHARS.match(text[a - 1]):
        a -= 1
    while b < len(text) and _WORD_CHARS.match(text[b]):
        b += 1
    while b > a and text[b - 1] in ".,;:/":
        b -= 1
    return a, b


def link_segments(text: str, links: list[dict],
                  used: set | None = None) -> list[tuple[str, str | None]]:
    """Split `text` into (chunk, url-or-None) pieces. Uses the original file's
    link targets first (e.g. the word "GitHub" pointing at github.com/you),
    then makes bare emails and web addresses clickable."""
    spans: list[tuple[int, int, str]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e, _ in spans)

    for link in sorted(links, key=lambda l: -len(l.get("text", ""))):
        anchor = (link.get("text") or "").strip(" |•·,;:/")
        key = (anchor.lower(), link["url"])
        if len(anchor) < 2 or (used is not None and key in used):
            continue  # like the original, link each anchor once (its first appearance)
        i = text.find(anchor)
        if i < 0:
            continue
        a, b = _snap_to_word(text, i, i + len(anchor))
        if free(a, b):
            spans.append((a, b, link["url"]))
            if used is not None:
                used.add(key)
    for m in EMAIL_RE.finditer(text):
        if free(m.start(), m.end()):
            spans.append((m.start(), m.end(), "mailto:" + m.group()))
    for m in URL_RE.finditer(text):
        end = m.start() + len(m.group().rstrip(".)"))
        if free(m.start(), end):
            spans.append((m.start(), end, _normalise_url(m.group())))

    out, pos = [], 0
    for a, b, url in sorted(spans):
        if a > pos:
            out.append((text[pos:a], None))
        out.append((text[a:b], url))
        pos = b
    if pos < len(text):
        out.append((text[pos:], None))
    return out or [(text, None)]


# ------------------------------------------------------------------ layout

@dataclass(frozen=True)
class Layout:
    """Sizes in points / inches. Tried in order until the resume fits one page."""
    body: float
    leading: float
    name: float
    heading: float
    section_gap: float
    margin_tb: float
    margin_lr: float


LAYOUTS = [
    Layout(10.5, 13.0, 17, 11.5, 8, 0.6, 0.7),
    Layout(10.0, 12.2, 16, 11.0, 6, 0.55, 0.65),
    Layout(9.5, 11.6, 15, 10.5, 5, 0.5, 0.6),
    Layout(9.0, 11.0, 14, 10.0, 4, 0.45, 0.55),
    Layout(8.5, 10.3, 13, 9.5, 3, 0.4, 0.5),  # floor: smaller stops being readable
]
LINK_COLOR = "1155CC"


# ------------------------------------------------------------------ DOCX

def _bottom_border(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in {"val": "single", "sz": "6", "space": "1", "color": "999999"}.items():
        bottom.set(qn(f"w:{k}"), v)
    borders.append(bottom)
    p_pr.append(borders)


def _add_hyperlink(paragraph, text: str, url: str, size: float, bold: bool = False) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    for tag, attrs in (("w:color", {"w:val": LINK_COLOR}), ("w:u", {"w:val": "single"}),
                       ("w:sz", {"w:val": str(int(size * 2))})):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        rpr.append(el)
    if bold:
        rpr.append(OxmlElement("w:b"))
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _write(paragraph, text: str, links: list[dict], size: float, bold: bool = False,
           used: set | None = None) -> None:
    for chunk, url in link_segments(text, links, used):
        if url:
            _add_hyperlink(paragraph, chunk, url, size, bold)
        else:
            run = paragraph.add_run(chunk)
            run.bold = bold
            run.font.size = Pt(size)


def render_docx(model: ResumeModel, layout: Layout | None = None) -> bytes:
    lay = layout or fit_one_page(model)[0]
    doc = Document()
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Inches(lay.margin_tb)
        section.left_margin = section.right_margin = Inches(lay.margin_lr)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(lay.body)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = Pt(lay.leading)
    doc.styles["List Bullet"].paragraph_format.line_spacing = Pt(lay.leading)

    used: set = set()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = Pt(lay.name * 1.2)
    run = p.add_run(model.name)
    run.bold = True
    run.font.size = Pt(lay.name)

    for line in model.contact:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _write(p, line, model.links, lay.body - 0.5, used=used)

    for section in model.sections:
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(lay.section_gap)
        h.paragraph_format.space_after = Pt(2)
        r = h.add_run(section.title.upper())
        r.bold = True
        r.font.size = Pt(lay.heading)
        _bottom_border(h)

        for line in section.lines:
            if line.kind == "bullet":
                p = doc.add_paragraph(style="List Bullet")
                p.paragraph_format.space_after = Pt(0)
                _write(p, line.text, model.links, lay.body, used=used)
            elif line.kind == "title":
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(lay.section_gap / 2)
                _write(p, line.text, model.links, lay.body, bold=True, used=used)
            else:
                _write(doc.add_paragraph(), line.text, model.links, lay.body, used=used)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ PDF

_FONTS_READY = False


def _register_fonts() -> None:
    """Vera ships with reportlab and is embedded, so its bullet "•" extracts as
    text. reportlab's built-in Helvetica draws "•" as an unmapped glyph that ATS
    read as "(cid:127)", the exact problem the checker warns about. So bullets
    always use Vera, and body text uses Helvetica (narrower, so more fits on one
    page) unless the text has characters Helvetica can't show."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))
    pdfmetrics.registerFont(TTFont("Vera-Bold", "VeraBd.ttf"))
    _FONTS_READY = True


def _all_text(model: ResumeModel) -> str:
    parts = [model.name, *model.contact]
    for s in model.sections:
        parts.append(s.title)
        parts.extend(l.text for l in s.lines)
    return "\n".join(parts)


def _needs_unicode_font(model: ResumeModel) -> bool:
    try:
        _all_text(model).encode("cp1252")
        return False
    except UnicodeEncodeError:
        return True


def _markup(text: str, links: list[dict], used: set | None = None) -> str:
    out = []
    for chunk, url in link_segments(text, links, used):
        if url:
            out.append(f'<a href="{escape(url, {chr(34): "&quot;"})}" color="#{LINK_COLOR}">'
                       f"<u>{escape(chunk)}</u></a>")
        else:
            out.append(escape(chunk))
    return "".join(out)


def _build_pdf(model: ResumeModel, lay: Layout) -> tuple[bytes, int]:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate

    _register_fonts()
    regular, bold = ("Vera", "Vera-Bold") if _needs_unicode_font(model) else ("Helvetica", "Helvetica-Bold")

    base = ParagraphStyle("base", fontName=regular, fontSize=lay.body, leading=lay.leading,
                          bulletFontName="Vera")
    styles = {
        "name": ParagraphStyle("name", parent=base, fontName=bold, fontSize=lay.name,
                               leading=lay.name * 1.2, alignment=TA_CENTER),
        "contact": ParagraphStyle("contact", parent=base, fontSize=lay.body - 0.5, alignment=TA_CENTER),
        "heading": ParagraphStyle("heading", parent=base, fontName=bold, fontSize=lay.heading,
                                  leading=lay.heading * 1.2, spaceBefore=lay.section_gap, spaceAfter=1),
        "title": ParagraphStyle("title", parent=base, fontName=bold, spaceBefore=lay.section_gap / 2),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=3),
        "text": base,
    }

    used: set = set()
    story = [Paragraph(escape(model.name), styles["name"])]
    story += [Paragraph(_markup(c, model.links, used), styles["contact"]) for c in model.contact]
    for section in model.sections:
        story.append(Paragraph(escape(section.title.upper()), styles["heading"]))
        story.append(HRFlowable(width="100%", thickness=0.6, color="#999999", spaceAfter=2))
        for line in section.lines:
            if line.kind == "bullet":
                story.append(Paragraph(_markup(line.text, model.links, used), styles["bullet"],
                                       bulletText="•"))
            else:
                story.append(Paragraph(_markup(line.text, model.links, used), styles[line.kind]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=lay.margin_lr * inch, rightMargin=lay.margin_lr * inch,
                            topMargin=lay.margin_tb * inch, bottomMargin=lay.margin_tb * inch,
                            title=model.name, author=model.name)
    doc.build(story)
    return buf.getvalue(), doc.page


def fit_one_page(model: ResumeModel) -> tuple[Layout, int]:
    """First layout (most comfortable first) whose PDF fits on one page.
    Returns the tightest layout and its page count if nothing fits."""
    pages = 0
    for lay in LAYOUTS:
        _, pages = _build_pdf(model, lay)
        if pages <= 1:
            return lay, 1
    return LAYOUTS[-1], pages


def render_pdf(model: ResumeModel, layout: Layout | None = None) -> bytes:
    lay = layout or fit_one_page(model)[0]
    return _build_pdf(model, lay)[0]
