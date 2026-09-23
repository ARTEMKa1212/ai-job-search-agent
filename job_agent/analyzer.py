from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .models import CandidateProfile, Job, JobAnalysis, RequirementAnalysis

SKILLS = {
    "python": "Python", "sql": "SQL", "docker": "Docker", "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL", "fastapi": "FastAPI", "flask": "Flask", "pytest": "pytest",
    "linux": "Linux", "aws": "AWS", "git": "Git", "ci/cd": "CI/CD", "rest api": "APIs",
    "restful": "APIs", "api": "APIs", "pandas": "data analysis", "automation": "automation",
    "llm": "AI agents", "artificial intelligence": "AI agents", "machine learning": "machine learning",
    "javascript": "JavaScript", "typescript": "TypeScript", "java": "Java", "c#": "C#",
    "kubernetes": "Kubernetes", "terraform": "Terraform", "azure": "Azure", "gcp": "GCP",
    "golang": "Go", "react": "React", "node.js": "Node.js", "ruby": "Ruby", "php": "PHP",
    "data annotation": "AI output evaluation", "evaluation": "AI output evaluation",
}
FAST_HOURS = {"SQL": 8, "Docker": 6, "PostgreSQL": 8, "FastAPI": 8, "Flask": 6,
              "pytest": 5, "Linux": 6, "CI/CD": 8, "APIs": 6, "Git": 4}


class Analyzer(ABC):
    @abstractmethod
    def analyze(self, job: Job, profile: CandidateProfile) -> JobAnalysis: ...


class HeuristicAnalyzer(Analyzer):
    def analyze(self, job: Job, profile: CandidateProfile) -> JobAnalysis:
        text = f"{job.title}\n{job.description}".lower()
        found: list[str] = []
        for needle, canonical in SKILLS.items():
            if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text) and canonical not in found:
                found.append(canonical)

        requirements: list[RequirementAnalysis] = []
        strengths: list[str] = []
        learning: list[str] = []
        known, achievable, blocking = 0, 0, 0
        for skill in found:
            status = _profile_skill(profile, skill)
            required = bool(re.search(rf"(?:required|must|essential)[^.\n]{{0,80}}{re.escape(skill.lower())}", text))
            importance = "high" if required else "medium"
            if status == "KNOW":
                gap, hours, blocks = "KNOW", 0, False
                known += int(required or skill.lower() in job.title.lower())
                achievable += int(required or skill.lower() in job.title.lower())
                strengths.append(skill)
            elif status == "LEARN_FAST" or skill in FAST_HOURS:
                gap, hours, blocks = "LEARN_FAST", FAST_HOURS.get(skill, 8), False
                achievable += int(required or skill.lower() in job.title.lower())
                if required:
                    learning.append(f"{skill}: {hours}h focused practice")
            else:
                gap, hours, blocks = "LEARNABLE", 20, required
                blocking += int(blocks)
            requirements.append(RequirementAnalysis(skill, required, importance, status, gap, hours, blocks))

        years = _required_years(text)
        risks: list[str] = []
        if years > profile.commercial_experience_years:
            requirements.append(RequirementAnalysis(
                f"{years}+ years commercial experience", True, "high",
                f"{profile.commercial_experience_years} years", "EXPERIENCE_GAP", 0, years >= 3,
            ))
            risks.append(f"Role asks for {years}+ years; projects do not replace commercial experience.")
            blocking += int(years >= 3)

        senior_title = bool(re.search(r"\b(senior|lead|principal|staff|manager|architect|head of)\b", job.title.lower()))
        if senior_title and years == 0:
            requirements.append(RequirementAnalysis(
                "senior-level commercial ownership", True, "high",
                "project experience", "EXPERIENCE_GAP", 0, True,
            ))
            risks.append("Title indicates senior-level ownership beyond the current profile.")
            blocking += 2

        advanced_role = bool(re.search(
            r"\b(?:leverage your expertise|very proficient|complex platforms?|pivotal role|"
            r"extensive experience|proven track record|highly scalable)\b", text
        ))
        if advanced_role and profile.commercial_experience_years == 0 and not senior_title:
            requirements.append(RequirementAnalysis(
                "production-level commercial experience", True, "high", "project experience",
                "EXPERIENCE_GAP", 0, True,
            ))
            risks.append("Description expects production ownership or expertise beyond project experience.")
            blocking += 2

        residency = re.search(r"resident in (?:the )?united kingdom for (?:the last )?(\d+) consecutive years", text)
        if residency:
            required_residency = int(residency.group(1))
            if profile.uk_residency_years < required_residency:
                requirements.append(RequirementAnalysis(
                    f"{required_residency} consecutive years UK residency", True, "high",
                    f"approximately {profile.uk_residency_years:g} year(s)", "EXPERIENCE_GAP", 0, True,
                ))
                risks.append(
                    f"HARD FILTER: requires {required_residency} consecutive years of UK residency; "
                    f"profile has approximately {profile.uk_residency_years:g}."
                )
                blocking += 5

        if re.search(r"native(?:-level| or near-native)? fluency in english|native english", text):
            level = profile.language_levels.get("English", "UNCONFIRMED")
            if level.upper() not in {"NATIVE", "NEAR_NATIVE"}:
                requirements.append(RequirementAnalysis(
                    "native or near-native English", True, "high", level,
                    "EXPERIENCE_GAP", 0, True,
                ))
                risks.append("USER CONFIRMATION REQUIRED: native or near-native English is a stated requirement.")
                blocking += 3

        target_overlap = any(term.lower() in text for role in profile.target_roles for term in role.lower().split() if len(term) > 4)
        remote = any(word in text for word in ("remote", "work from home", "distributed"))
        scored_skills = [r for r in requirements if r.skill in found and (r.required or r.skill.lower() in job.title.lower())]
        denominator = max(len(scored_skills), 1)
        skill_now = known / denominator
        skill_week = achievable / denominator
        direct_target = any(role.lower() in job.title.lower() or job.title.lower() in role.lower()
                            for role in profile.target_roles)
        entry_friendly = bool(re.search(r"\b(?:no previous professional experience|no experience required|entry.level|junior|graduate)\b", text))
        no_scored_skills = not scored_skills
        current = round(25 + 35 * skill_now + 15 * direct_target + 10 * target_overlap + 10 * remote
                        + 15 * entry_friendly + 10 * no_scored_skills - 12 * blocking)
        seven = round(25 + 35 * skill_week + 15 * direct_target + 10 * target_overlap + 10 * remote
                      + 15 * entry_friendly + 10 * no_scored_skills - 10 * blocking)
        current, seven = _clamp(current), _clamp(max(current, seven))
        recommendation = "STRONG APPLY" if seven >= 75 else "STRETCH APPLY" if seven >= 55 else "SKIP"
        reason = _reason(recommendation, known, len(learning), blocking)
        return JobAnalysis(current, seven, recommendation, reason, strengths, requirements,
                           risks, learning, "heuristic")


class OpenAICompatibleAnalyzer(Analyzer):
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model

    def analyze(self, job: Job, profile: CandidateProfile) -> JobAnalysis:
        schema_instruction = """Return only JSON with keys current_match, seven_day_match (0-100),
recommendation (STRONG APPLY, STRETCH APPLY, or SKIP), reason, strengths (strings), risks (strings),
learning_tasks (strings), requirements. Each requirement has skill, required (bool), importance,
current_status, gap_type (KNOW, LEARN_FAST, LEARNABLE, EXPERIENCE_GAP), estimated_learning_hours
(integer), blocks_application (bool). Never invent candidate experience. Treat learnable tools as APPLY NOW + LEARN."""
        prompt = f"{schema_instruction}\nCANDIDATE:\n{json.dumps(profile.__dict__ if hasattr(profile, '__dict__') else {k: getattr(profile, k) for k in profile.__dataclass_fields__}, ensure_ascii=False)}\nJOB:\n{job.title}\n{job.description}"
        body = json.dumps({"model": self.model, "messages": [
            {"role": "system", "content": "You are a strict, honest junior-career job matching analyst."},
            {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}).encode()
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        content = result["choices"][0]["message"]["content"]
        data = json.loads(_extract_json(content))
        data["provider"] = "llm"
        return JobAnalysis.from_dict(data)


def _profile_skill(profile: CandidateProfile, skill: str) -> str:
    for name, status in profile.skills.items():
        if name.casefold() == skill.casefold():
            return status
    return "UNKNOWN"


def _required_years(text: str) -> int:
    matches = re.findall(r"(\d+)\s*\+?\s*(?:years?|yrs?)", text)
    return max((int(value) for value in matches), default=0)


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _reason(rec: str, known: int, fast: int, blocking: int) -> str:
    if rec == "STRONG APPLY":
        return f"Strong overlap ({known} known requirements); {fast} gaps are quickly learnable."
    if rec == "STRETCH APPLY":
        return f"Worth applying honestly: {fast} gaps can be reduced this week; review {blocking} material gaps."
    return f"Too many material gaps ({blocking}) for this week's application focus."


def _extract_json(value: str) -> str:
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM did not return a JSON object")
    return value[start:end + 1]
