from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .analyzer import _extract_json
from .models import ApplicationPackage, CandidateProfile, Job, JobAnalysis


class PackageGenerator(ABC):
    @abstractmethod
    def generate(self, job: Job, profile: CandidateProfile, analysis: JobAnalysis) -> ApplicationPackage: ...


class HonestTemplateGenerator(PackageGenerator):
    def generate(self, job: Job, profile: CandidateProfile, analysis: JobAnalysis) -> ApplicationPackage:
        role_text = f"{job.title} {job.description}".lower()
        evaluator_role = any(term in role_text for term in ("evaluation", "evaluator", "annotation", "annotator", "ai model responses", "ai-generated content"))
        research_role = any(term in role_text for term in ("online data analyst", "online research", "digital maps", "relevance"))
        if evaluator_role:
            preferred = ["AI output evaluation", "prompt engineering", "AI agents", "attention to detail",
                         "guideline-based work", "independent remote work", "online research", "Python"]
        elif research_role:
            preferred = ["online research", "attention to detail", "guideline-based work", "data analysis",
                         "Pandas", "Microsoft Excel", "independent remote work", "AI output evaluation"]
        else:
            preferred = analysis.strengths + list(profile.skills)
        relevant = [skill for skill in preferred if skill in profile.skills][:8]
        if not relevant:
            relevant = analysis.strengths or list(profile.skills)[:5]
        project_bullets = [f"Built {project[0].lower() + project[1:]}" for project in profile.projects[:3]]
        learning = ", ".join(task.split(":", 1)[0] for task in analysis.learning_tasks[:3])
        learning_sentence = f" I am currently strengthening {learning} for this type of role." if learning else ""
        if evaluator_role:
            summary = (
                "Computer Science graduate experienced in using and reviewing AI systems for programming, "
                "research, analysis and multi-step workflows. Skilled at interpreting prompts, checking AI "
                "outputs, following structured instructions and working independently with close attention "
                "to accuracy. Uses English, Ukrainian and Russian, and has the right to work in the UK."
            )
            fit_sentence = (
                "My work with AI-assisted technical workflows requires me to interpret objectives, provide "
                "clear contextual instructions, review generated responses, identify errors and improve outputs."
            )
        elif research_role:
            summary = (
                "Computer Science graduate with experience in structured-data processing, online research, "
                "AI-assisted analysis and careful review of technical information. Comfortable following "
                "detailed guidelines, comparing information for relevance and accuracy, and working "
                "independently. Based in the UK with the right to work."
            )
            fit_sentence = (
                "My data-analysis projects and AI-assisted research involve checking information carefully, "
                "identifying patterns, comparing outputs and turning raw information into clear conclusions."
            )
        else:
            summary = (
                "Computer Science graduate with hands-on Python project experience across automation, "
                "external APIs, AI-agent workflows and data analysis. Eligible to work in the UK and "
                "seeking a practical role where project-built engineering skills can create value quickly."
            )
            fit_sentence = f"The role aligns particularly well with my experience in {', '.join(relevant[:4])}."
        cover = (
            f"Dear {job.company} hiring team,\n\n"
            f"I am applying for the {job.title} position. I am a Computer Science graduate with "
            "hands-on Python experience from projects involving automation, external APIs, AI-agent "
            "workflows and data processing. "
            f"{fit_sentence}"
            f"{learning_sentence}\n\n"
            "While my experience is project-based rather than long-term commercial experience, I can "
            "demonstrate working systems, learn unfamiliar tools quickly and communicate gaps honestly. "
            "I have the right to work in the UK and would welcome the opportunity to discuss how I can "
            f"contribute.\n\nKind regards,\n{profile.name}"
        )
        if evaluator_role:
            interest = (
                "This role matches my practical experience using AI tools, reviewing generated outputs and "
                "working through structured technical tasks carefully. It is an opportunity to contribute "
                "to better AI systems while developing professional evaluation experience."
            )
        elif research_role:
            interest = (
                "This role matches my experience with data analysis, independent research and careful technical "
                "work. I am interested in applying these skills to improve the quality and relevance of "
                "information used by real digital products."
            )
        else:
            interest = (
                f"The {job.title} role matches my focus on Python, automation and practical software delivery. "
                "It offers a strong opportunity to apply skills built through working projects while growing in a professional team."
            )
        answers = {
            "Why are you interested in this role?": (
                interest
            ),
            "Do you have the right to work in the UK?": "Yes, I have the right to work in the UK.",
            "How many years of commercial experience do you have?": (
                f"{profile.commercial_experience_years} years of commercial experience. My relevant experience "
                "comes from hands-on Python projects involving APIs, automation, AI workflows and data analysis."
            ),
        }
        interviews = [f"Prepare a concrete example demonstrating {skill}." for skill in relevant[:4]]
        interviews.extend(f"Review {task}." for task in analysis.learning_tasks[:3])
        return ApplicationPackage(summary, relevant, project_bullets, cover,
                                  f"{analysis.recommendation}: {analysis.reason}", answers,
                                  analysis.risks, interviews, "heuristic")


class OpenAICompatiblePackageGenerator(PackageGenerator):
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model

    def generate(self, job: Job, profile: CandidateProfile, analysis: JobAnalysis) -> ApplicationPackage:
        facts = {key: getattr(profile, key) for key in profile.__dataclass_fields__}
        prompt = f"""Create honest application materials for this vacancy. Never invent employment,
years, metrics, technologies, qualifications, responsibilities, or achievements. Use only supplied facts.
Return JSON with professional_summary, cv_skills_order (strings), cv_project_bullets (strings),
cover_letter, application_summary, common_answers (object), risks (strings), interview_points (strings).
CANDIDATE: {json.dumps(facts, ensure_ascii=False)}
ANALYSIS: {json.dumps(analysis.to_dict(), ensure_ascii=False)}
JOB: {job.title} at {job.company}\n{job.description}"""
        body = json.dumps({"model": self.model, "messages": [
            {"role": "system", "content": "You write concise, truthful UK job applications."},
            {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}).encode()
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        data = json.loads(_extract_json(result["choices"][0]["message"]["content"]))
        data["provider"] = "llm"
        return ApplicationPackage.from_dict(data)
