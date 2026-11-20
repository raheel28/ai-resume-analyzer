"""Apply accepted bullet changes to a resume.

Two paths:
  * DOCX, keep layout: replace paragraph text inside the user's own file, so
    fonts, spacing and list formatting stay exactly as they were.
  * Anything else: change the extracted lines, then rebuild the resume from
    a clean single-column ATS template (see render.py).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from docx import Document

from app.ai.guard import PLACEHOLDER_RE, normalise
from app.parsing.sections import _ALIAS_LOOKUP, SECTION_ALIASES, normalise_heading

MAX_CHANGES = 30
MAX_LEN = 400
MAX_SKILLS = 20
SKILL_HEADINGS = SECTION_ALIASES["skills"]
# Any "[...]" left in a replacement is an unfilled placeholder, whatever its length.
UNFILLED_RE = re.compile(r"\[[^\]]*\]")
LITERAL_BULLET_RE = re.compile(r"^\s*([•▪●◦*\-–•·])\s*")


@dataclass
class Change:
    original: str
    replacement: str


@dataclass
class ApplyResult:
    applied: list[str]
    not_found: list[str]
    skills_added: list[str] = None

    def __post_init__(self):
        self.skills_added = self.skills_added or []


def validate_changes(raw: object) -> list[Change]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("changes must be a list")
    if len(raw) > MAX_CHANGES:
        raise ValueError(f"At most {MAX_CHANGES} changes at a time")
    changes = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each change needs 'original' and 'replacement'")
        original = str(item.get("original", "")).strip()
        replacement = " ".join(str(item.get("replacement", "")).split())
        if not original or not replacement:
            raise ValueError("Each change needs 'original' and 'replacement'")
        if len(replacement) > MAX_LEN:
            raise ValueError("A replacement bullet is too long")
        if UNFILLED_RE.search(replacement):
            raise ValueError(f"Fill in the [placeholders] first: \"{replacement[:60]}…\"")
        changes.append(Change(original, replacement))
    return changes


def _matches(text: str, target: str) -> bool:
    """Exact match after normalising, or the target covers most of the line
    (the AI sometimes quotes a bullet without its trailing clause)."""
    norm = normalise(text)
    if not norm:
        return False
    return norm == target or (target in norm and len(target) >= 0.8 * len(norm))


def _with_bullet(old: str, new: str) -> str:
    m = LITERAL_BULLET_RE.match(old)
    return f"{m.group(1)} {new}" if m else new


def apply_to_lines(lines: list[str], changes: list[Change]) -> tuple[list[str], ApplyResult]:
    out = list(lines)
    result = ApplyResult([], [])
    for ch in changes:
        target = normalise(ch.original)
        for i, line in enumerate(out):
            if _matches(line, target):
                out[i] = _with_bullet(line, ch.replacement)
                result.applied.append(ch.original)
                break
        else:
            result.not_found.append(ch.original)
    return out, result


def _all_paragraphs(document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def edit_docx_in_place(data: bytes, changes: list[Change],
                       skills: list[str] | None = None) -> tuple[bytes, ApplyResult]:
    document = Document(io.BytesIO(data))
    result = ApplyResult([], [])
    paragraphs = list(_all_paragraphs(document))

    for ch in changes:
        target = normalise(ch.original)
        for p in paragraphs:
            if p.runs and _matches(p.text, target):
                new_text = _with_bullet(p.text, ch.replacement)
                # Keep the first run's formatting (font, size, bold), drop the rest.
                p.runs[0].text = new_text
                for run in p.runs[1:]:
                    run._element.getparent().remove(run._element)
                result.applied.append(ch.original)
                break
        else:
            result.not_found.append(ch.original)

    if skills:
        result.skills_added = add_skills_docx(document, skills)

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue(), result


# ------------------------------------------------------------------ skills

def validate_skills(raw: object) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_SKILLS:
        raise ValueError(f"add_skills must be a list of at most {MAX_SKILLS} skills")
    out = []
    for item in raw:
        skill = " ".join(str(item).split())
        if not skill or len(skill) > 40 or any(c in skill for c in "<>{}[]"):
            raise ValueError(f"Invalid skill: {str(item)[:40]!r}")
        if skill.lower() not in (s.lower() for s in out):
            out.append(skill)
    return out


def _is_skills_heading(text: str) -> bool:
    return normalise_heading(text) in SKILL_HEADINGS


def _is_any_heading(text: str) -> bool:
    return normalise_heading(text) in _ALIAS_LOOKUP


def _new_skills(existing_text: str, skills: list[str]) -> list[str]:
    from app.jd.lexicon import mentions

    return [s for s in skills if not mentions(existing_text, s)]


def add_skills_to_lines(lines: list[str], skills: list[str]) -> tuple[list[str], list[str]]:
    """Append skills to the first line of the Skills section (or add a section)."""
    todo = _new_skills("\n".join(lines), skills)
    if not todo:
        return lines, []
    out = list(lines)
    for i, line in enumerate(out):
        if _is_skills_heading(line):
            if i + 1 < len(out) and not _is_any_heading(out[i + 1]):
                out[i + 1] = out[i + 1].rstrip(" ,.") + ", " + ", ".join(todo)
            else:
                out.insert(i + 1, ", ".join(todo))
            return out, todo
    return out + ["SKILLS", ", ".join(todo)], todo


def add_skills_docx(document, skills: list[str]) -> list[str]:
    paragraphs = document.paragraphs
    todo = _new_skills("\n".join(p.text for p in paragraphs), skills)
    if not todo:
        return []
    for i, p in enumerate(paragraphs):
        if _is_skills_heading(p.text):
            for target in paragraphs[i + 1:]:
                if target.text.strip():
                    if _is_any_heading(target.text):
                        # Empty Skills section: put the list right before the next heading.
                        target.insert_paragraph_before(", ".join(todo))
                        return todo
                    run = target.runs[-1] if target.runs else target.add_run("")
                    run.text = run.text.rstrip(" ,.") + ", " + ", ".join(todo)
                    return todo
            break
    document.add_paragraph("SKILLS").runs[0].bold = True
    document.add_paragraph(", ".join(todo))
    return todo
