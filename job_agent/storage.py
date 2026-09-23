from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from .models import ApplicationPackage, Job, JobAnalysis


class Storage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL, company TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual', salary TEXT NOT NULL DEFAULT '',
                    remote_status TEXT NOT NULL DEFAULT 'unknown', status TEXT NOT NULL DEFAULT 'NEW',
                    date_found TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS job_analysis (
                    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                    analysis_json TEXT NOT NULL, provider TEXT NOT NULL,
                    analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS application_materials (
                    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                    materials_json TEXT NOT NULL, provider TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS applications (
                    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, date_applied TEXT, response TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def add_job(self, job: Job) -> int:
        self.init()
        with self.connect() as db:
            if job.url:
                existing = db.execute("SELECT id FROM jobs WHERE url=?", (job.url,)).fetchone()
                if existing:
                    return int(existing[0])
            cursor = db.execute(
                "INSERT INTO jobs(title, company, description, url, source, salary, remote_status, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (job.title, job.company, job.description, job.url, job.source,
                 job.salary, job.remote_status, job.status),
            )
            return int(cursor.lastrowid)

    def get_job(self, job_id: int) -> Job:
        self.init()
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job {job_id} not found")
        return Job(**{key: row[key] for key in Job.__dataclass_fields__})

    def list_jobs(self) -> list[dict]:
        self.init()
        with self.connect() as db:
            rows = db.execute(
                "SELECT j.id, j.title, j.company, j.status, a.analysis_json "
                "FROM jobs j LEFT JOIN job_analysis a ON a.job_id=j.id ORDER BY j.id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def unanalyzed_job_ids(self) -> list[int]:
        self.init()
        with self.connect() as db:
            rows = db.execute(
                "SELECT j.id FROM jobs j LEFT JOIN job_analysis a ON a.job_id=j.id "
                "WHERE a.job_id IS NULL ORDER BY j.id"
            ).fetchall()
        return [int(row[0]) for row in rows]

    def shortlist(self, minimum_score: int = 55, limit: int = 20) -> list[dict]:
        self.init()
        with self.connect() as db:
            rows = db.execute(
                "SELECT j.id, j.title, j.company, j.url, j.salary, j.remote_status, j.status, a.analysis_json "
                "FROM jobs j JOIN job_analysis a ON a.job_id=j.id"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            analysis = json.loads(item.pop("analysis_json"))
            excluded = {"REJECTED_BY_ME", "REJECTED", "EXPIRED", "INELIGIBLE"}
            if analysis["seven_day_match"] >= minimum_score and item["status"] not in excluded:
                item.update(analysis)
                result.append(item)
        return sorted(result, key=lambda item: (item["seven_day_match"], item["current_match"]), reverse=True)[:limit]

    def learning_gaps(self) -> list[dict]:
        self.init()
        counts: dict[str, dict] = {}
        with self.connect() as db:
            rows = db.execute("SELECT analysis_json FROM job_analysis").fetchall()
        for row in rows:
            analysis = json.loads(row[0])
            for requirement in analysis.get("requirements", []):
                if requirement.get("gap_type") not in ("LEARN_FAST", "LEARNABLE"):
                    continue
                skill = requirement["skill"]
                item = counts.setdefault(skill, {"skill": skill, "jobs": 0, "hours": requirement.get("estimated_learning_hours", 0)})
                item["jobs"] += 1
                item["hours"] = min(item["hours"], requirement.get("estimated_learning_hours", item["hours"]))
        return sorted(counts.values(), key=lambda item: (-item["jobs"], item["hours"]))

    def pipeline_counts(self) -> list[tuple[str, int]]:
        self.init()
        with self.connect() as db:
            rows = db.execute("SELECT status, COUNT(*) AS total FROM jobs GROUP BY status ORDER BY total DESC").fetchall()
        return [(row["status"], row["total"]) for row in rows]

    def save_analysis(self, job_id: int, analysis: JobAnalysis) -> None:
        payload = json.dumps(analysis.to_dict(), ensure_ascii=False)
        with self.connect() as db:
            db.execute(
                "INSERT INTO job_analysis(job_id, analysis_json, provider) VALUES (?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET analysis_json=excluded.analysis_json, "
                "provider=excluded.provider, analyzed_at=CURRENT_TIMESTAMP",
                (job_id, payload, analysis.provider),
            )
            db.execute("UPDATE jobs SET status='ANALYZED' WHERE id=?", (job_id,))

    def get_analysis(self, job_id: int) -> JobAnalysis | None:
        with self.connect() as db:
            row = db.execute("SELECT analysis_json FROM job_analysis WHERE job_id=?", (job_id,)).fetchone()
        return JobAnalysis.from_dict(json.loads(row[0])) if row else None

    def set_status(self, job_id: int, status: str) -> None:
        self.get_job(job_id)
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
            db.execute(
                "INSERT INTO applications(job_id, status) VALUES (?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, updated_at=CURRENT_TIMESTAMP",
                (job_id, status),
            )

    def save_materials(self, job_id: int, package: ApplicationPackage) -> None:
        payload = json.dumps(package.to_dict(), ensure_ascii=False)
        with self.connect() as db:
            db.execute(
                "INSERT INTO application_materials(job_id, materials_json, provider) VALUES (?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET materials_json=excluded.materials_json, "
                "provider=excluded.provider, created_at=CURRENT_TIMESTAMP",
                (job_id, payload, package.provider),
            )

    def get_materials(self, job_id: int) -> ApplicationPackage | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT materials_json FROM application_materials WHERE job_id=?", (job_id,)
            ).fetchone()
        return ApplicationPackage.from_dict(json.loads(row[0])) if row else None
