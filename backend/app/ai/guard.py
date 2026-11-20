"""Server-side checks on AI-suggested rewrites.

LLMs happily "improve" a bullet by inventing a metric ("reduced latency by
45%") or a technology the candidate never used ("using Kubernetes"). On a
resume that's lying, so we reject any rewrite that introduces:

  * a number that isn't in the original bullet (placeholders like [X] are fine), or
  * a technical term / proper noun that appears nowhere in the resume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER_RE = re.compile(r"\[[^\]]{1,20}\]")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
# Tokens that look like names of things: capitalised mid-sentence, or containing
# digits / tech punctuation (C++, Node.js, GPT-4, S3).
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*")

# Capitalised words that are fine to introduce.
COMMON_CAPS = {"i", "a", "the", "an", "api", "apis", "ui", "ux", "ci", "cd", "ci/cd", "ml", "ai",
               "llm", "rest", "sql", "json", "http", "end-to-end", "b2b", "b2c", "kpi", "kpis"}


# Claims an LLM likes to add that are facts, not wording. Each must already be
# in the ORIGINAL bullet to appear in the rewrite. (Found by evals/run_guard.py.)
CLAIM_PATTERNS = {
    "invented quantity": re.compile(
        r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|"
        r"forty|fifty|hundreds?|thousands?|millions?|billions?|dozens?|"
        r"doubled?|doubling|tripled?|tripling|quadrupled?|halved?|halving|twice|thrice|"
        r"tenfold|twofold|threefold|\w+fold|several\s+times|\d*x\s+(?:faster|more|fewer|less))\b", re.I),
    "invented scale or business impact": re.compile(
        r"\b(?:company[-\s]wide|organi[sz]ation[-\s]wide|enterprise[-\s]wide|globally|global|worldwide|"
        r"revenue|profit|sales\s+growth|cost\s+savings?|saved\s+the\s+company|across\s+all|"
        r"all\s+(?:company|users|customers|teams))\b", re.I),
    "invented leadership": re.compile(
        r"\b(?:led|lead|leading|managed|managing|mentored|mentoring|supervised|supervising|"
        r"spearheaded|headed|directed|oversaw|coached|coaching|team\s+of|cross[-\s]functional\s+team)\b",
        re.I),
    "invented recognition": re.compile(
        r"\b(?:awards?|awarded|won|winning|winner|first\s+place|prize|published|publication|"
        r"patents?|promoted|promotion|recogni[sz]ed|featured|acclaimed|hackathon)\b", re.I),
}


# Lowercase parts of a compound that still name a technology.
TECHISH = {"js", "sql", "db", "api", "aws", "gcp", "ml", "ai"}


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    needs_input: bool = False  # suggestion contains [X] placeholders for the user to fill in


def normalise(s: str) -> str:
    s = re.sub(r"^[•▪●◦*\-–•·]\s*", "", s.strip())
    return " ".join(s.lower().split())


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER_RE.findall(PLACEHOLDER_RE.sub(" ", text))}


def _named_terms(text: str) -> set[str]:
    text = PLACEHOLDER_RE.sub(" ", text)
    terms = set()
    for i, match in enumerate(TOKEN_RE.finditer(text)):
        tok = match.group().rstrip(".,;:/-")
        if not tok:
            continue
        looks_named = (i > 0 and tok[0].isupper()) or any(c.isdigit() or c in "+#." for c in tok)
        if looks_named and tok.lower() not in COMMON_CAPS:
            terms.add(tok.lower())
    return terms


def _known_term(term: str, resume_lower: str) -> bool:
    """A term is fine if it's in the resume. Hyphenated compounds such as
    "LLM-powered" or "preference-based" are fine if their named parts are."""
    if term in resume_lower:
        return True
    parts = [p for p in re.split(r"[-/]", term) if p]
    if len(parts) > 1:
        return all(p in resume_lower or (p.isalpha() and p.islower() and len(p) > 2 and p not in TECHISH)
                   for p in parts)
    return False


def check_rewrite(original: str, suggested: str, resume_text: str) -> GuardResult:
    if normalise(original) == normalise(suggested):
        return GuardResult(False, "unchanged")

    new_numbers = _numbers(suggested) - _numbers(original)
    if new_numbers:
        return GuardResult(False, f"invented number(s): {', '.join(sorted(new_numbers))}")

    for label, pattern in CLAIM_PATTERNS.items():
        new = {m.group().lower() for m in pattern.finditer(suggested)} - \
              {m.group().lower() for m in pattern.finditer(original)}
        if new:
            return GuardResult(False, f"{label}: {', '.join(sorted(new))}")

    resume_lower = resume_text.lower()
    invented = sorted(t for t in _named_terms(suggested) if not _known_term(t, resume_lower))
    if invented:
        return GuardResult(False, f"term(s) not in your resume: {', '.join(invented)}")

    # Known technologies written in lowercase ("kubernetes", "typescript") slip
    # past the capitalisation heuristic, so check them against the skill list too.
    from app.jd.lexicon import skills_in

    new_tech = sorted(set(skills_in(suggested)) - set(skills_in(resume_text)))
    if new_tech:
        return GuardResult(False, f"technology not in your resume: {', '.join(new_tech)}")

    return GuardResult(True, needs_input=bool(PLACEHOLDER_RE.search(suggested)))
