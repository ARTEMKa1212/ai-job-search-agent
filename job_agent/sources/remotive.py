from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request

from ..models import Job
from .base import JobSource

TARGET_TERMS = (
    "python", "automation", "ai trainer", "ai evaluator", "llm", "data analyst",
    "data engineer", "qa automation", "technical support", "api integration",
    "backend", "software developer", "artificial intelligence",
)
TITLE_TERMS = ("python", "automation", "ai ", "artificial intelligence", "llm", "data analyst",
               "data engineer", "qa", "technical support", "api", "backend")
SENIOR_TERMS = ("senior", "lead", "principal", "staff", "manager", "architect", "head of")
ALLOWED_LOCATIONS = ("worldwide", "anywhere", "uk", "united kingdom", "europe", "emea", "england")


class RemotiveSource(JobSource):
    endpoint = "https://remotive.com/api/remote-jobs"

    def collect(self, limit: int = 50) -> list[Job]:
        # No query string: some CDN caches have historically ignored query parameters.
        url = self.endpoint
        request = urllib.request.Request(url, headers={"User-Agent": "PersonalJobSearchAgent/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Remotive collection failed: {exc}") from exc
        jobs = []
        for item in payload.get("jobs", []):
            title = str(item.get("title", ""))
            title_lower = title.lower()
            searchable = f"{title} {self._text(item.get('description', ''))}".lower()
            location = str(item.get("candidate_required_location", "Worldwide"))
            if not any(term in searchable for term in TARGET_TERMS):
                continue
            if not any(term in title_lower for term in TITLE_TERMS):
                continue
            if any(term in title_lower for term in SENIOR_TERMS):
                continue
            if location and not any(place in location.lower() for place in ALLOWED_LOCATIONS):
                continue
            jobs.append(Job(
                None, title or "Untitled vacancy",
                str(item.get("company_name", "Unknown company")),
                self._text(str(item.get("description", ""))), str(item.get("url", "")),
                "remotive", str(item.get("salary", "")), "remote",
            ))
            if len(jobs) >= limit:
                break
        return jobs

    @staticmethod
    def _text(value: str) -> str:
        value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
        value = re.sub(r"(?s)<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(value)).strip()
