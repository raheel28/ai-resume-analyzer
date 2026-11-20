"""Rule-based ATS checks.

Every check is deterministic: the same resume always gets the same result.
Each returns a score in [0, 1]; the scorer weights and combines them.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable

from app.parsing.extract import ExtractedDocument
from app.parsing.sections import SectionedResume

from .action_verbs import ACTION_VERBS


@dataclass
class CheckResult:
    id: str
    category: str  # "parseability" | "structure" | "content"
    title: str
    score: float  # 0..1
    weight: float
    severity: str  # "critical" | "warning" | "tip" | "pass"
    message: str
    details: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 0.8

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


@dataclass
class Context:
    doc: ExtractedDocument
    resume: SectionedResume
    bullets: list[str]


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def has_phone(text: str) -> bool:
    # Require 9+ digits so year ranges like "2022 - 2026" don't count.
    return any(sum(c.isdigit() for c in m.group()) >= 9 for m in PHONE_RE.finditer(text))
LINK_RE = re.compile(r"(linkedin\.com/in/|github\.com/)", re.I)
BULLET_PREFIX = re.compile(r"^[•▪●◦‣⁃∙*\-–•·]\s*")
NUMBER_RE = re.compile(r"\d|%|€|\$|£")
PRONOUN_RE = re.compile(r"\b(I|me|my|mine|myself)\b")
PRIVATE_USE_RE = re.compile(r"[-]")  # icon fonts, often unreadable by ATS

MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_PATTERNS = {
    "Mon YYYY": re.compile(rf"\b{MONTH}\s+\d{{4}}\b", re.I),
    "MM/YYYY": re.compile(r"\b(0?[1-9]|1[0-2])/\d{4}\b"),
    "YYYY-MM": re.compile(r"\b\d{4}-(0[1-9]|1[0-2])\b"),
}


def _sev(score: float, critical_below: float = 0.4) -> str:
    if score >= 0.8:
        return "pass"
    return "critical" if score < critical_below else "warning"


def find_bullets(resume: SectionedResume) -> list[str]:
    """Bullet-like lines from experience and projects sections."""
    lines = [ln for name in ("experience", "projects") for ln in resume.sections.get(name, [])]
    marked = [BULLET_PREFIX.sub("", ln).strip() for ln in lines if BULLET_PREFIX.match(ln)]
    if marked:
        return [b for b in marked if b]
    # No bullet symbols (e.g. Word list formatting was lost): fall back to
    # sentence-like lines, skipping job-title lines that contain dates.
    return [ln for ln in lines
            if len(ln.split()) >= 6 and not any(p.search(ln) for p in DATE_PATTERNS.values())]


# ------------------------------------------------------------ parseability

def check_text_extractable(ctx: Context) -> CheckResult:
    wc = ctx.doc.word_count
    if ctx.doc.file_type == "docx":
        # DOCX text is always machine-readable; shortness is the length check's job.
        score = 1.0 if wc >= 30 else 0.0
        msg = f"{wc} words extracted." if score else "The document appears to be empty."
        return CheckResult("text_extractable", "parseability", "Text can be read", score, 4,
                           _sev(score, 0.6), msg)
    score = 1.0 if wc >= 200 else 0.5 if wc >= 80 else 0.0
    msg = (f"{wc} words extracted." if score == 1.0 else
           f"Only {wc} words could be read. If this is a scanned or image-based "
           "file, ATS will see it as almost empty. Export a text-based PDF or DOCX.")
    return CheckResult("text_extractable", "parseability", "Text can be read", score, 4,
                       _sev(score, 0.6), msg)


def check_tables(ctx: Context) -> CheckResult:
    n = ctx.doc.table_count
    score = 1.0 if n == 0 else 0.4
    msg = ("No tables." if n == 0 else
           f"{n} table(s) found. Many ATS read tables cell by cell and scramble the order. "
           "Use plain lines and tabs instead.")
    return CheckResult("tables", "parseability", "No tables", score, 2, _sev(score), msg)


def check_columns(ctx: Context) -> CheckResult:
    score = 0.3 if ctx.doc.multi_column else 1.0
    msg = ("Single-column layout." if score == 1.0 else
           "Looks like a multi-column layout. ATS often read across both columns line by "
           "line, mixing your sections together. Use a single column.")
    return CheckResult("columns", "parseability", "Single column", score, 3, _sev(score), msg)


def check_images(ctx: Context) -> CheckResult:
    n = ctx.doc.image_count
    score = 1.0 if n == 0 else 0.6
    msg = ("No images or graphics." if n == 0 else
           f"{n} image(s)/graphic(s) found. ATS ignore them, so any text inside "
           "(skill bars, icons, logos) is lost.")
    return CheckResult("images", "parseability", "No images", score, 1, _sev(score), msg)


def check_header_footer(ctx: Context) -> CheckResult:
    hf = ctx.doc.header_footer_text
    has_contact = bool(EMAIL_RE.search(hf) or has_phone(hf))
    score = 0.3 if has_contact else 1.0
    msg = ("Contact details are in the main body." if score == 1.0 else
           "Your contact details are in the page header/footer, which some ATS skip. "
           "Move them into the body.")
    return CheckResult("header_footer", "parseability", "Contact info not in header/footer",
                       score, 2, _sev(score), msg)


def check_special_chars(ctx: Context) -> CheckResult:
    icons = len(PRIVATE_USE_RE.findall(ctx.doc.text))
    cids = ctx.doc.undecodable_glyphs
    if not icons and not cids:
        return CheckResult("special_chars", "parseability", "No unreadable symbols", 1.0, 1,
                           "pass", "No unreadable symbols.")
    parts = []
    if icons:
        parts.append(f"{icons} icon-font character(s) (e.g. phone/email icons). "
                     "Replace them with plain words like 'Email:'.")
    if cids:
        parts.append(f"{cids} symbol(s), usually bullet points, use a font character that "
                     "can't be converted to text, so some ATS show them as garbage like "
                     "'(cid:127)'. Use a standard bullet (•) or a plain hyphen.")
    return CheckResult("special_chars", "parseability", "No unreadable symbols", 0.6, 1,
                       "tip", " ".join(parts))


# ------------------------------------------------------------ structure

def check_contact(ctx: Context) -> CheckResult:
    text = ctx.doc.text + "\n" + ctx.doc.header_footer_text
    found = {
        "email": bool(EMAIL_RE.search(text)),
        "phone": has_phone(text),
        "LinkedIn/GitHub": bool(LINK_RE.search(text)),
    }
    missing = [k for k, v in found.items() if not v]
    score = 1.0 - 0.4 * (not found["email"]) - 0.3 * (not found["phone"]) - 0.2 * (not found["LinkedIn/GitHub"])
    msg = "Email, phone and profile link found." if not missing else "Missing: " + ", ".join(missing) + "."
    return CheckResult("contact", "structure", "Contact information", max(score, 0), 3,
                       _sev(score), msg)


def check_core_sections(ctx: Context) -> CheckResult:
    required = ["experience", "education", "skills"]
    # Students often have Projects instead of Experience; accept either.
    present = {
        "experience": ctx.resume.has("experience") or ctx.resume.has("projects"),
        "education": ctx.resume.has("education"),
        "skills": ctx.resume.has("skills"),
    }
    missing = [s for s in required if not present[s]]
    score = 1.0 - len(missing) / len(required)
    msg = ("Experience/Projects, Education and Skills sections found." if not missing else
           "Couldn't find a section for: " + ", ".join(missing) +
           ". Use standard headings so ATS can file your details correctly.")
    return CheckResult("core_sections", "structure", "Standard sections", score, 4,
                       _sev(score, 0.5), msg, details=list(ctx.resume.heading_map.keys()))


def check_heading_names(ctx: Context) -> CheckResult:
    odd = ctx.resume.unrecognised_headings
    score = 1.0 if not odd else max(0.5, 1 - 0.15 * len(odd))
    msg = ("All headings use standard names." if not odd else
           "These headings aren't standard and may not be recognised: " + ", ".join(odd[:6]))
    return CheckResult("heading_names", "structure", "Recognisable headings", score, 1,
                       "pass" if score >= 0.8 else "tip", msg, details=odd)


def check_length(ctx: Context) -> CheckResult:
    wc, pages = ctx.doc.word_count, ctx.doc.page_count
    details = []
    if 350 <= wc <= 900:
        score = 1.0
    elif 250 <= wc < 350 or 900 < wc <= 1200:
        score = 0.7
    else:
        score = 0.4
    if pages and pages > 2:
        score = min(score, 0.5)
        details.append(f"{pages} pages")
    msg = (f"{wc} words, a good length." if score == 1.0 else
           f"{wc} words. Aim for roughly 400-800 words (1 page for students/new grads, "
           "2 max).")
    return CheckResult("length", "structure", "Length", score, 2, _sev(score), msg, details)


def check_date_format(ctx: Context) -> CheckResult:
    used = [name for name, pat in DATE_PATTERNS.items() if pat.search(ctx.doc.text)]
    if not used:
        score, msg = 0.6, "No dates found. Add start/end dates (e.g. 'Jan 2024 - Present')."
    elif len(used) == 1:
        score, msg = 1.0, f"Dates use one consistent format ({used[0]})."
    else:
        score, msg = 0.7, "Mixed date formats: " + ", ".join(used) + ". Pick one."
    return CheckResult("date_format", "structure", "Consistent dates", score, 1,
                       _sev(score), msg, used)


# ------------------------------------------------------------ content

def check_action_verbs(ctx: Context) -> CheckResult:
    if not ctx.bullets:
        return CheckResult("action_verbs", "content", "Bullets start with action verbs", 0.5, 3,
                           "warning", "No bullet points found (no Experience or Projects section was recognised).")
    weak = [b for b in ctx.bullets if b.split()[0].lower().strip(",.:;") not in ACTION_VERBS]
    ratio = 1 - len(weak) / len(ctx.bullets)
    score = min(1.0, ratio / 0.8)  # 80%+ strong starts counts as full marks
    msg = (f"{ratio:.0%} of bullets start with a strong action verb." +
           ("" if score >= 0.8 else " Start bullets with verbs like Built, Led, Reduced, Designed."))
    return CheckResult("action_verbs", "content", "Bullets start with action verbs", score, 3,
                       _sev(score), msg, details=weak[:8])


def check_quantified(ctx: Context) -> CheckResult:
    if not ctx.bullets:
        return CheckResult("quantified", "content", "Results are quantified", 0.5, 3,
                           "warning", "No bullet points found to check.")
    with_numbers = [b for b in ctx.bullets if NUMBER_RE.search(b)]
    ratio = len(with_numbers) / len(ctx.bullets)
    score = min(1.0, ratio / 0.5)  # half the bullets with a number = full marks
    without = [b for b in ctx.bullets if b not in with_numbers]
    msg = (f"{ratio:.0%} of bullets include a number." +
           ("" if score >= 0.8 else " Add scale or impact: users, %, time saved, requests/sec."))
    return CheckResult("quantified", "content", "Results are quantified", score, 3,
                       _sev(score), msg, details=without[:8])


def check_bullet_length(ctx: Context) -> CheckResult:
    long = [b for b in ctx.bullets if len(b.split()) > 35]
    score = 1.0 if not long else max(0.4, 1 - 0.2 * len(long))
    msg = ("Bullets are concise." if not long else
           f"{len(long)} bullet(s) over 35 words. Keep each to 1-2 lines.")
    return CheckResult("bullet_length", "content", "Concise bullets", score, 1,
                       _sev(score), msg, details=long[:5])


def check_pronouns(ctx: Context) -> CheckResult:
    body = "\n".join(ctx.bullets) or ctx.doc.text
    hits = PRONOUN_RE.findall(body)
    score = 1.0 if len(hits) <= 1 else 0.6
    msg = ("No first-person pronouns in bullets." if score == 1.0 else
           f"Found {len(hits)} first-person pronouns (I/my/me). Resume bullets usually drop them.")
    return CheckResult("pronouns", "content", "No first-person pronouns", score, 1,
                       "pass" if score == 1.0 else "tip", msg)


ALL_CHECKS: list[Callable[[Context], CheckResult]] = [
    check_text_extractable, check_tables, check_columns, check_images,
    check_header_footer, check_special_chars,
    check_contact, check_core_sections, check_heading_names, check_length, check_date_format,
    check_action_verbs, check_quantified, check_bullet_length, check_pronouns,
]
