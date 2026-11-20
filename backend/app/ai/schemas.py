"""Shapes the model must return. Kept small and flat: smaller schemas give
more reliable structured output."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(description="1 (poor) to 10 (excellent)")
    reason: str = Field(description="One sentence, specific to this resume")

    @field_validator("score", mode="before")
    @classmethod
    def clamp(cls, v):
        # Clamp instead of failing the whole response over one out-of-range number.
        try:
            return max(1, min(10, int(round(float(v)))))
        except (TypeError, ValueError):
            return 5


class BulletRewrite(BaseModel):
    original: str = Field(description="The bullet exactly as it appears in the resume")
    suggested: str = Field(description="Improved bullet. Use [X] placeholders for unknown numbers")
    reason: str


class ModelReview(BaseModel):
    """Raw model output, before the server-side guard runs."""
    rubric: list[CriterionScore]
    strengths: list[str]
    improvements: list[str]
    rewrites: list[BulletRewrite]


class JDRequirement(BaseModel):
    skill: str = Field(description="Short name of a skill/technology/qualification, e.g. 'Kubernetes'")
    importance: str = Field(description="'required' or 'nice'")


class ModelMatchReview(BaseModel):
    """Raw model output for resume-vs-job-description review."""
    rubric: list[CriterionScore]
    strengths: list[str]
    gaps: list[str]
    requirements: list[JDRequirement]
    rewrites: list[BulletRewrite]
