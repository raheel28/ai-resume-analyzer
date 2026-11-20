"""Rule-based job description match: which of the JD's skills does the resume show?"""

from __future__ import annotations

import re

from app.parsing.extract import UnsupportedFileError, extract

from .lexicon import mentions, skills_in

MIN_JD_CHARS = 80
MAX_JD_CHARS = 20_000
MAX_JD_FILE_BYTES = 2 * 1024 * 1024

# Text after one of these headings/phrases lists nice-to-haves, not requirements.
NICE_TO_HAVE_RE = re.compile(
    r"nice[\s-]to[\s-]haves?|preferred(?:\s+qualifications|\s+skills)?|bonus(?:\s+points)?"
    r"|desirable|would\s+be\s+a\s+plus|is\s+a\s+plus|good\s+to\s+have|pluses",
    re.I,
)
WEIGHTS = {"required": 2, "nice": 1}


class JDError(ValueError):
    pass


def read_jd(text: str | None, filename: str | None, data: bytes | None) -> str:
    if data:
        if len(data) > MAX_JD_FILE_BYTES:
            raise JDError("Job description file is larger than 2 MB")
        name = (filename or "").lower()
        if name.endswith((".txt", ".md")):
            jd = data.decode("utf-8", errors="replace")
        else:
            try:
                jd = extract(name, data).text
            except UnsupportedFileError as exc:
                raise JDError("Job description must be pasted text or a .pdf, .docx or .txt file") from exc
            except Exception as exc:
                raise JDError("Couldn't read the job description file") from exc
    else:
        jd = text or ""
    jd = jd.strip()
    if len(jd) < MIN_JD_CHARS:
        raise JDError("The job description is too short. Paste the full posting.")
    return jd[:MAX_JD_CHARS]


def classify(jd: str) -> dict[str, str]:
    """Skill -> 'required' | 'nice'. A skill is nice-to-have only if it is
    mentioned *only* after a nice-to-have marker."""
    m = NICE_TO_HAVE_RE.search(jd)
    main, extra = (jd[: m.start()], jd[m.start():]) if m else (jd, "")
    result = {}
    for skill in skills_in(jd):
        result[skill] = "required" if mentions(main, skill) else "nice"
    return result


def keyword_match(resume_text: str, jd: str) -> dict:
    wanted = classify(jd)
    rows = [
        {"skill": s, "importance": imp, "found": mentions(resume_text, s)}
        for s, imp in wanted.items()
    ]
    rows.sort(key=lambda r: (r["importance"] != "required", r["found"], r["skill"].lower()))

    total = sum(WEIGHTS[r["importance"]] for r in rows)
    got = sum(WEIGHTS[r["importance"]] for r in rows if r["found"])
    score = round(100 * got / total) if total else None

    req = [r for r in rows if r["importance"] == "required"]
    return {
        "score": score,
        "skills": rows,
        "required_found": sum(r["found"] for r in req),
        "required_total": len(req),
        "missing": [r["skill"] for r in rows if not r["found"]],
        "note": None if rows else
            "No known technical skills found in this job description, so there's no keyword "
            "score. The AI review below still compares it with your resume.",
    }
