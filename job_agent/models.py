from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

GapType = Literal["KNOW", "LEARN_FAST", "LEARNABLE", "EXPERIENCE_GAP"]


@dataclass(slots=True)
class CandidateProfile:
    name: str
    location: str
    work_authorization: list[str]
    remote_preferred: bool
    education: list[str]
    skills: dict[str, str]
    projects: list[str]
    commercial_experience_years: int
    target_roles: list[str]
    email: str = ""
    phone: str = ""
    languages: list[str] = field(default_factory=list)
    employment: list[str] = field(default_factory=list)
    degree_details: str = ""
    uk_residency_years: float = 0
    language_levels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateProfile":
        required = {"name", "location", "work_authorization", "remote_preferred", "education",
                    "skills", "projects", "commercial_experience_years", "target_roles"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Missing profile fields: {', '.join(sorted(missing))}")
        optional = {"email", "phone", "languages", "employment", "degree_details", "uk_residency_years", "language_levels"}
        values = {key: data[key] for key in required}
        values.update({key: data[key] for key in optional if key in data})
        return cls(**values)


@dataclass(slots=True)
class Job:
    id: int | None
    title: str
    company: str
    description: str
    url: str = ""
    source: str = "manual"
    salary: str = ""
    remote_status: str = "unknown"
    status: str = "NEW"


@dataclass(slots=True)
class RequirementAnalysis:
    skill: str
    required: bool
    importance: str
    current_status: str
    gap_type: GapType
    estimated_learning_hours: int
    blocks_application: bool


@dataclass(slots=True)
class JobAnalysis:
    current_match: int
    seven_day_match: int
    recommendation: str
    reason: str
    strengths: list[str] = field(default_factory=list)
    requirements: list[RequirementAnalysis] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    learning_tasks: list[str] = field(default_factory=list)
    provider: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobAnalysis":
        requirements = [RequirementAnalysis(**item) for item in data.get("requirements", [])]
        return cls(
            current_match=_score(data.get("current_match")),
            seven_day_match=_score(data.get("seven_day_match")),
            recommendation=str(data.get("recommendation", "STRETCH APPLY")),
            reason=str(data.get("reason", "Review manually.")),
            strengths=list(data.get("strengths", [])),
            requirements=requirements,
            risks=list(data.get("risks", [])),
            learning_tasks=list(data.get("learning_tasks", [])),
            provider=str(data.get("provider", "llm")),
        )


@dataclass(slots=True)
class ApplicationPackage:
    professional_summary: str
    cv_skills_order: list[str]
    cv_project_bullets: list[str]
    cover_letter: str
    application_summary: str
    common_answers: dict[str, str]
    risks: list[str]
    interview_points: list[str]
    provider: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationPackage":
        return cls(
            professional_summary=str(data.get("professional_summary", "")),
            cv_skills_order=list(data.get("cv_skills_order", [])),
            cv_project_bullets=list(data.get("cv_project_bullets", [])),
            cover_letter=str(data.get("cover_letter", "")),
            application_summary=str(data.get("application_summary", "")),
            common_answers=dict(data.get("common_answers", {})),
            risks=list(data.get("risks", [])),
            interview_points=list(data.get("interview_points", [])),
            provider=str(data.get("provider", "heuristic")),
        )


def _score(value: Any) -> int:
    score = int(value)
    if not 0 <= score <= 100:
        raise ValueError("Match scores must be between 0 and 100")
    return score
