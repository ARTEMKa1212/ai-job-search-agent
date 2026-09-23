from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request

from ..models import Job
from .base import JobSource

TARGET_TITLE_TERMS = (
    "python", "automation", "ai ", "artificial intelligence", "machine learning",
    "llm", "data analyst", "data engineer", "qa", "quality assurance",
    "technical support", "application support", "api", "backend", "software developer",
)
EXCLUDED_SENIORITY = ("senior", "lead", "principal", "staff", "manager", "architect", "head of", "director")


class ArbeitnowUKSource(JobSource):
    endpoint = "https://www.arbeitnow.co.uk/api/job-board-api"

    def collect(self, limit: int = 50) -> list[Job]:
        jobs: list[Job] = []
        for page in range(1, 11):
            request = urllib.request.Request(
                f"{self.endpoint}?page={page}", headers={"User-Agent": "PersonalJobSearchAgent/0.1"}
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.load(response)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Arbeitnow UK collection failed: {exc}") from exc
            items = payload.get("data", [])
            for item in items:
                title = str(item.get("title", ""))
                lowered = title.lower()
                if not any(term in lowered for term in TARGET_TITLE_TERMS):
                    continue
                if any(term in lowered for term in EXCLUDED_SENIORITY):
                    continue
                if not bool(item.get("remote")):
                    continue
                description = self._text(str(item.get("description", "")))
                jobs.append(Job(
                    None, title, str(item.get("company_name", "Unknown company")), description,
                    str(item.get("url", "")), "arbeitnow_uk", "", "remote",
                ))
                if len(jobs) >= limit:
                    return jobs
            links = payload.get("links", {})
            if not items or not links.get("next"):
                break
        return jobs

    @staticmethod
    def _text(value: str) -> str:
        # The API HTML is entity-escaped once before tags are removed.
        value = html.unescape(value)
        value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
        value = re.sub(r"(?s)<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(value)).strip()
