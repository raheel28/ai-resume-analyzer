import io
import json

import pytest
from docx import Document

from app.ai.match_review import review_match
from app.edit.apply import add_skills_docx, add_skills_to_lines, validate_skills
from app.jd.lexicon import mentions
from app.jd.match import JDError, keyword_match, read_jd
from app.llm.client import FakeClient
from app.parsing.extract import extract

from . import fixtures

JD = """Junior Software Engineer. Build backend services in Python and Go (Golang), design
RESTful APIs, work with PostgreSQL and Redis, deploy with Docker on AWS, use Git and CI/CD.
Strong data structures and algorithms. Go to our careers page. The rest of the team is remote.
Nice to have: Kubernetes, Kafka, machine learning."""
RESUME = extract("cv.docx", fixtures.good_docx()).text


def by_skill(result):
    return {r["skill"]: r for r in result["skills"]}


def test_keyword_match_required_vs_nice_and_found():
    res = keyword_match(RESUME, JD)
    rows = by_skill(res)
    assert rows["Python"] == {"skill": "Python", "importance": "required", "found": True}
    assert rows["AWS"]["found"] is False and rows["AWS"]["importance"] == "required"
    assert rows["Kubernetes"]["importance"] == "nice"
    assert 0 < res["score"] < 100
    assert "AWS" in res["missing"] and "Python" not in res["missing"]


def test_ambiguous_words_are_not_skills():
    assert not mentions("Go to our careers page. The rest of the team", "Go")
    assert not mentions("the rest of the team", "REST APIs")
    assert mentions("Python, Go, Rust", "Go")
    assert not mentions("JavaScript developer", "Java")
    assert mentions("Built a Node.js API", "Node.js") and mentions("JS and HTML", "JavaScript")


def test_match_score_is_deterministic():
    assert keyword_match(RESUME, JD) == keyword_match(RESUME, JD)


def test_read_jd_text_and_files():
    assert read_jd(JD, None, None).startswith("Junior")
    assert read_jd("", "jd.txt", JD.encode()) == JD.strip()
    doc = Document(); doc.add_paragraph(JD); buf = io.BytesIO(); doc.save(buf)
    assert "PostgreSQL" in read_jd("", "jd.docx", buf.getvalue())
    with pytest.raises(JDError, match="too short"):
        read_jd("Python dev", None, None)
    with pytest.raises(JDError):
        read_jd("", "jd.png", b"x" * 200)


def test_add_skills_to_existing_skills_line_skips_duplicates():
    lines = ["Jane", "SKILLS", "Python, Docker", "EDUCATION", "UCD"]
    out, added = add_skills_to_lines(lines, ["AWS", "docker", "Kafka"])
    assert added == ["AWS", "Kafka"]
    assert out[2] == "Python, Docker, AWS, Kafka"


def test_add_skills_creates_section_when_missing():
    out, added = add_skills_to_lines(["Jane", "EXPERIENCE", "• Built x"], ["AWS"])
    assert out[-2:] == ["SKILLS", "AWS"] and added == ["AWS"]


def test_add_skills_docx_in_place():
    document = Document(io.BytesIO(fixtures.good_docx()))
    added = add_skills_docx(document, ["AWS", "Python"])
    assert added == ["AWS"]
    texts = [p.text for p in document.paragraphs]
    i = texts.index("SKILLS")
    assert texts[i + 1].endswith(", AWS")


def test_validate_skills():
    assert validate_skills(["AWS", " aws ", "Kafka"]) == ["AWS", "Kafka"]
    with pytest.raises(ValueError):
        validate_skills(["<script>"])


def test_ai_match_review_guard_and_requirements():
    bullet = "Migrated nightly batch jobs to Airflow, cutting failed runs from 12 to 1 per month"
    payload = {
        "rubric": [{"criterion": c, "score": 6, "reason": "r"}
                   for c in ("skills_match", "experience_relevance", "seniority_fit", "impact")],
        "strengths": ["Python backend work"], "gaps": ["No AWS"],
        "requirements": [{"skill": "AWS", "importance": "required"},
                         {"skill": "3+ years backend", "importance": "required"},
                         {"skill": "Airflow", "importance": "nice to have"}],
        "rewrites": [
            {"original": bullet, "reason": "job-relevant first",
             "suggested": "Cut failed nightly runs from 12 to 1 per month by migrating batch jobs to Airflow"},
            {"original": bullet, "reason": "adds JD skill",
             "suggested": "Migrated batch jobs to Airflow on AWS, cutting failed runs from 12 to 1 per month"},
        ],
    }
    out = review_match(FakeClient(lambda s, p: json.dumps(payload)), RESUME, [bullet], JD,
                       keyword_skills=["AWS", "Python"])
    assert out["score"] == 60
    assert len(out["rewrites"]) == 1  # the one that slipped in AWS is rejected
    assert "aws" in out["rejected_rewrites"][0]["reason"]
    extra = {r["skill"]: r for r in out["other_requirements"]}
    assert "AWS" not in extra  # already in keyword list
    assert extra["Airflow"] == {"skill": "Airflow", "importance": "nice", "found": True}
    assert extra["3+ years backend"]["found"] is False


def test_ai_requirements_reworded_duplicates_are_dropped():
    payload = {
        "rubric": [], "strengths": [], "gaps": [], "rewrites": [],
        "requirements": [{"skill": n, "importance": "required"} for n in
                         ("Go (Golang)", "RESTful APIs", "GitHub Actions / CI/CD",
                          "Data structures and algorithms", "3+ years backend", "Kubernetes on EKS")],
    }
    out = review_match(FakeClient(lambda s, p: json.dumps(payload)), RESUME, [], JD,
                       keyword_skills=["Go", "REST APIs", "CI/CD", "Git", "Data structures & algorithms"])
    names = [r["skill"] for r in out["other_requirements"]]
    assert names == ["3+ years backend", "Kubernetes on EKS"]  # Kubernetes isn't in the keyword list
