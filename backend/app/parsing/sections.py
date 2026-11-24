from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTION_ALIASES: dict[str, set[str]] = {
    "summary": {"summary", "professional summary", "profile", "about me", "objective",
                "career objective", "career summary", "personal statement"},
    "experience": {"experience", "work experience", "professional experience",
                   "employment", "employment history", "work history", "internships",
                   "internship", "relevant experience"},
    "education": {"education", "academic background", "academics", "qualifications",
                  "education and training"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "skills summary",
               "core competencies", "technologies", "tech stack"},
    "projects": {"projects", "personal projects", "academic projects", "key projects",
                 "selected projects"},
    "certifications": {"certifications", "certificates", "licenses", "licenses and certifications"},
    "achievements": {"achievements", "awards", "honors", "honours", "awards and achievements",
                     "accomplishments"},
    "publications": {"publications", "research"},
    "volunteering": {"volunteering", "volunteer experience", "leadership",
                     "extracurricular activities", "activities"},
    "languages": {"languages"},
    "interests": {"interests", "hobbies"},
}

_ALIAS_LOOKUP = {alias: canon for canon, aliases in SECTION_ALIASES.items() for alias in aliases}
_STRIP = re.compile(r"[^a-z& ]+")


@dataclass
class SectionedResume:
    header: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)
    heading_map: dict[str, str] = field(default_factory=dict)
    unrecognised_headings: list[str] = field(default_factory=list)
    titles: dict[str, str] = field(default_factory=dict)

    def has(self, name: str) -> bool:
        return bool(self.sections.get(name))


def normalise_heading(line: str) -> str:
    s = line.lower().replace("&", " and ")
    s = _STRIP.sub(" ", s)
    return " ".join(s.split())


def _looks_like_heading(line: str) -> bool:
    words = line.split()
    if not 1 <= len(words) <= 4 or len(line) > 40:
        return False
    if line.rstrip().endswith((".", ",")):
        return False
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and (line.isupper() or line.rstrip().endswith(":"))


def split_sections(lines: list[str]) -> SectionedResume:
    result = SectionedResume()
    current: str | None = None

    for line in lines:
        norm = normalise_heading(line)
        canon = _ALIAS_LOOKUP.get(norm)
        if canon:
            current = canon
            result.heading_map[line] = canon
            result.sections.setdefault(canon, [])
            result.titles.setdefault(canon, line.rstrip(":").strip())
            continue
        if _looks_like_heading(line) and current is not None:
            result.unrecognised_headings.append(line)
            current = f"other:{norm}"
            result.sections.setdefault(current, [])
            result.titles.setdefault(current, line.rstrip(":").strip())
            continue
        if current is None:
            result.header.append(line)
        else:
            result.sections[current].append(line)

    return result
