from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(description="1 (poor) to 10 (excellent)")
    reason: str = Field(description="One sentence, specific to this resume")

    @field_validator("score", mode="before")
    @classmethod
    def clamp(cls, v):
        try:
            return max(1, min(10, int(round(float(v)))))
        except (TypeError, ValueError):
            return 5


class BulletRewrite(BaseModel):
    original: str = Field(description="The bullet exactly as it appears in the resume")
    suggested: str = Field(description="Improved bullet. Use [X] placeholders for unknown numbers")
    reason: str


class ModelReview(BaseModel):
    rubric: list[CriterionScore]
    strengths: list[str]
    improvements: list[str]
    rewrites: list[BulletRewrite]


class JDRequirement(BaseModel):
    skill: str = Field(description="Short name of a skill/technology/qualification, e.g. 'Kubernetes'")
    importance: str = Field(description="'required' or 'nice'")


class ModelMatchReview(BaseModel):
    rubric: list[CriterionScore]
    strengths: list[str]
    gaps: list[str]
    requirements: list[JDRequirement]
    rewrites: list[BulletRewrite]
