"""Turn an uploaded PDF or DOCX into plain text plus layout signals.

Layout signals (tables, images, columns, header/footer text) matter because
many ATS parsers read documents top-to-bottom as plain text and mangle
anything that isn't a simple single-column flow.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber
from docx import Document
from docx.oxml.ns import qn


class UnsupportedFileError(ValueError):
    pass


@dataclass
class ExtractedDocument:
    file_type: str  # "pdf" | "docx"
    text: str
    lines: list[str]
    page_count: int | None = None  # None for DOCX (not knowable without rendering)
    table_count: int = 0
    image_count: int = 0
    multi_column: bool = False
    header_footer_text: str = ""
    undecodable_glyphs: int = 0  # "(cid:N)" characters the PDF font couldn't map to text
    links: list[dict] = field(default_factory=list)  # [{"text": anchor text, "url": target}]
    warnings: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def extract(filename: str, data: bytes) -> ExtractedDocument:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    raise UnsupportedFileError("Only .pdf and .docx files are supported")


CID_RE = re.compile(r"\(cid:\d+\)")
LEADING_CID_RE = re.compile(r"^\s*(?:\(cid:\d+\)\s*)+")


def _clean_lines(raw: str) -> list[str]:
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


BULLET_START_RE = re.compile(r"^[\u2022\u25aa\u25cf\u25e6\u2023\u2043\u2219\uf0b7\uf0a7*\-–•·]\s")
DATE_HINT_RE = re.compile(r"\b(19|20)\d{2}\b|\bpresent\b", re.I)


def merge_wrapped_bullets(lines: list[str]) -> list[str]:
    """PDF text comes out one visual line at a time, so a bullet that wraps
    onto a second line is split in two. Join continuation lines back onto
    their bullet.

    A line is treated as a continuation when the previous line is (part of) a
    bullet and the line doesn't start a new bullet, isn't a heading, and either
    starts lowercase or follows a line with no closing full stop and has no
    date in it (job title / date lines have dates)."""
    out: list[str] = []
    in_bullet = False
    for ln in lines:
        if BULLET_START_RE.match(ln):
            out.append(ln)
            in_bullet = True
            continue
        is_heading = ln.isupper() or (len(ln.split()) <= 4 and ln.endswith(":"))
        prev = out[-1] if out else ""
        continuation = in_bullet and not is_heading and (
            ln[:1].islower()
            or (not prev.rstrip().endswith((".", "!", "?")) and not DATE_HINT_RE.search(ln))
        )
        if continuation:
            out[-1] = f"{prev} {ln}"
        else:
            out.append(ln)
            in_bullet = False
    return out


def _fix_cid(text: str) -> str:
    """pdfplumber emits "(cid:127)" for glyphs with no text mapping. At the start
    of a line it's almost always a bullet symbol; elsewhere drop it."""
    lines = [LEADING_CID_RE.sub("• ", ln) for ln in text.splitlines()]
    return CID_RE.sub("", "\n".join(lines))


# ---------------------------------------------------------------- PDF

def _extract_pdf(data: bytes) -> ExtractedDocument:
    texts: list[str] = []
    links: list[dict] = []
    tables = images = 0
    column_votes = 0

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = pdf.pages
        for page in pages:
            texts.append(page.extract_text() or "")
            tables += len(page.find_tables())
            images += len(page.images)
            if _pdf_page_looks_multicolumn(page):
                column_votes += 1
            links.extend(_pdf_links(page))
        page_count = len(pages)

    raw = "\n".join(texts)
    cid_count = len(CID_RE.findall(raw))
    text = _fix_cid(raw)
    doc = ExtractedDocument(
        file_type="pdf",
        text=text,
        lines=merge_wrapped_bullets(_clean_lines(text)),
        page_count=page_count,
        table_count=tables,
        image_count=images,
        multi_column=page_count > 0 and column_votes / page_count >= 0.5,
        undecodable_glyphs=cid_count,
        links=_dedupe_links(links),
    )
    if doc.word_count < 50:
        doc.warnings.append(
            "Very little text could be extracted. The PDF may be a scanned image, "
            "which most ATS cannot read."
        )
    return doc


def _pdf_links(page) -> list[dict]:
    """Link annotations with the text underneath them. Characters are matched by
    their centre point because link boxes are often slightly smaller than the text."""
    out = []
    for h in page.hyperlinks:
        url = h.get("uri")
        if not url:
            continue
        x0, x1, top, bottom = h["x0"] - 1, h["x1"] + 1, h["top"] - 2, h["bottom"] + 2

        def inside(obj, x0=x0, x1=x1, top=top, bottom=bottom):
            if obj.get("object_type") != "char":
                return False
            cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
            return x0 <= cx <= x1 and top <= cy <= bottom

        try:
            text = page.filter(inside).extract_text() or ""
        except Exception:
            text = ""
        # Link boxes often clip a letter or catch the "|" separator next to the word;
        # trim separators here, and render.py snaps the anchor to whole words.
        text = _fix_cid(" ".join(text.split())).strip(" •|·,;:/")
        out.append({"text": text, "url": url})
    return out


def _dedupe_links(links: list[dict]) -> list[dict]:
    seen, out = set(), []
    for link in links:
        key = (link["text"].lower(), link["url"])
        if link["url"] and key not in seen:
            seen.add(key)
            out.append(link)
    return out


def _pdf_page_looks_multicolumn(page) -> bool:
    """Heuristic: in a two-column layout, many text lines have a wide gap
    near the middle of the page between two runs of words."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    if len(words) < 40:
        return False

    width = float(page.width)
    rows: dict[int, list] = {}
    for w in words:
        rows.setdefault(round(float(w["top"]) / 3), []).append(w)

    gap_threshold = width * 0.08
    middle_lo, middle_hi = width * 0.25, width * 0.75
    split_rows = 0
    for row in rows.values():
        row.sort(key=lambda w: float(w["x0"]))
        for a, b in zip(row, row[1:]):
            gap = float(b["x0"]) - float(a["x1"])
            if gap > gap_threshold and middle_lo < float(b["x0"]) < middle_hi:
                split_rows += 1
                break

    # Right-aligned dates ("Jan 2024 – Present") create gaps too, but at the
    # far right; requiring the second run to start in the middle band filters
    # most of them out.
    return split_rows / max(len(rows), 1) > 0.3


# ---------------------------------------------------------------- DOCX

def _extract_docx(data: bytes) -> ExtractedDocument:
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several types for bad files
        raise UnsupportedFileError("Could not open this .docx file") from exc

    lines = [p.text for p in document.paragraphs]

    # Text inside tables is often skipped or scrambled by ATS, but we still
    # want it for analysis, so include it and flag the table separately.
    for table in document.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell.text.strip() and cell.text not in cells:  # merged cells repeat
                    cells.append(cell.text)
            lines.append(" | ".join(cells))

    hf_parts: list[str] = []
    multi_column = False
    for section in document.sections:
        for part in (section.header, section.footer):
            hf_parts.extend(p.text for p in part.paragraphs if p.text.strip())
        for cols in section._sectPr.findall(qn("w:cols")):
            if int(cols.get(qn("w:num"), "1")) > 1:
                multi_column = True

    links = []
    for el in document.element.body.iter(qn("w:hyperlink")):
        rid = el.get(qn("r:id"))
        rel = document.part.rels.get(rid) if rid else None
        if rel is not None and rel.is_external:
            text = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
            links.append({"text": text, "url": rel.target_ref})

    body = document.element.body
    images = len(body.findall(".//" + qn("w:drawing"))) + len(body.findall(".//" + qn("w:pict")))
    text_boxes = len(body.findall(".//" + qn("w:txbxContent")))

    text = "\n".join(lines)
    doc = ExtractedDocument(
        file_type="docx",
        text=text,
        lines=_clean_lines(text),
        table_count=len(document.tables),
        image_count=images,
        multi_column=multi_column,
        header_footer_text="\n".join(hf_parts),
        links=_dedupe_links(links),
    )
    if text_boxes:
        doc.warnings.append(
            f"Found {text_boxes} text box(es). Text boxes are often ignored by ATS parsers."
        )
    return doc
