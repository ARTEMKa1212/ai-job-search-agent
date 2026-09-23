from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .analyzer import HeuristicAnalyzer, OpenAICompatibleAnalyzer
from .config import load_dotenv, load_profile
from .generator import HonestTemplateGenerator, OpenAICompatiblePackageGenerator
from .models import Job, JobAnalysis
from .storage import Storage
from .sources import ArbeitnowUKSource, RemotiveSource


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="AI Job Search Agent MVP")
    root.add_argument("--db", default=None, help="SQLite database path")
    root.add_argument("--profile", default="profile.json")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    add = commands.add_parser("add", help="Save a manually supplied vacancy")
    _ingestion_args(add)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("job_id", type=int)
    analyze.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    show = commands.add_parser("show")
    show.add_argument("job_id", type=int)
    commands.add_parser("list")
    approve = commands.add_parser("approve", help="Approve and generate application materials")
    approve.add_argument("job_id", type=int)
    approve.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    reject = commands.add_parser("reject")
    reject.add_argument("job_id", type=int)
    generate = commands.add_parser("generate")
    generate.add_argument("job_id", type=int)
    generate.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    materials = commands.add_parser("materials")
    materials.add_argument("job_id", type=int)
    export = commands.add_parser("export", help="Export application package to Markdown")
    export.add_argument("job_id", type=int)
    export.add_argument("--output", help="Output .md path")
    status = commands.add_parser("status", help="Update application pipeline status")
    status.add_argument("job_id", type=int)
    status.add_argument("value", choices=("SHORTLISTED", "APPROVED", "APPLIED", "REJECTED",
                                          "NO_RESPONSE", "ASSESSMENT", "RECRUITER_CALL",
                                          "INTERVIEW", "OFFER", "EXPIRED", "INELIGIBLE"))
    collect = commands.add_parser("collect", help="Collect targeted remote vacancies")
    collect.add_argument("--source", choices=("all", "arbeitnow", "remotive"), default="all")
    collect.add_argument("--limit", type=int, default=25)
    commands.add_parser("learning", help="Rank skill gaps across analyzed jobs")
    commands.add_parser("stats", help="Show application pipeline counts")
    analyze_all = commands.add_parser("analyze-all", help="Analyze every new job")
    analyze_all.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    shortlist = commands.add_parser("shortlist", help="Show best analyzed vacancies")
    shortlist.add_argument("--minimum", type=int, default=55)
    shortlist.add_argument("--limit", type=int, default=20)
    run = commands.add_parser("run", help="Add, analyze and show in one command")
    _ingestion_args(run)
    run.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    return root


def _ingestion_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("--file", help="UTF-8 text file containing job description")
    command.add_argument("--description", help="Job description text")
    command.add_argument("--title", default="Untitled vacancy")
    command.add_argument("--company", default="Unknown company")
    command.add_argument("--url", default="")
    command.add_argument("--salary", default="")
    command.add_argument("--remote", default="unknown", choices=("remote", "hybrid", "onsite", "unknown"))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parser().parse_args(argv)
    store = Storage(args.db or os.getenv("JOB_AGENT_DB", "job_agent.db"))
    try:
        if args.command == "init":
            store.init(); print(f"Database ready: {store.path}")
        elif args.command in ("add", "run"):
            job_id = store.add_job(_job_from_args(args))
            print(f"Saved job #{job_id}")
            if args.command == "run":
                _analyze(store, job_id, args.profile, args.provider)
                _show(store, job_id)
        elif args.command == "analyze":
            _analyze(store, args.job_id, args.profile, args.provider)
            _show(store, args.job_id)
        elif args.command == "show":
            _show(store, args.job_id)
        elif args.command == "list":
            _list(store)
        elif args.command == "approve":
            store.set_status(args.job_id, "APPROVED")
            _generate(store, args.job_id, args.profile, args.provider)
            _materials(store, args.job_id)
        elif args.command == "reject":
            store.set_status(args.job_id, "REJECTED_BY_ME")
            print(f"Rejected job #{args.job_id}")
        elif args.command == "generate":
            _generate(store, args.job_id, args.profile, args.provider)
            _materials(store, args.job_id)
        elif args.command == "materials":
            _materials(store, args.job_id)
        elif args.command == "export":
            _export(store, args.job_id, args.output)
        elif args.command == "status":
            store.set_status(args.job_id, args.value)
            print(f"Job #{args.job_id}: {args.value}")
        elif args.command == "collect":
            sources = []
            if args.source in ("all", "arbeitnow"):
                sources.append(ArbeitnowUKSource())
            if args.source in ("all", "remotive"):
                sources.append(RemotiveSource())
            jobs = []
            errors = []
            for source in sources:
                try:
                    jobs.extend(source.collect(args.limit))
                except RuntimeError as exc:
                    errors.append(str(exc))
            ids = [store.add_job(job) for job in jobs]
            print(f"Collected {len(jobs)} targeted remote jobs; database IDs: {', '.join(map(str, ids)) or 'none'}")
            for error in errors:
                print(f"Source warning: {error}", file=sys.stderr)
        elif args.command == "learning":
            gaps = store.learning_gaps()
            if not gaps:
                print("No analyzed learning gaps yet.")
            for index, item in enumerate(gaps, 1):
                print(f"{index}. {item['skill']}: {item['jobs']} relevant job(s), ~{item['hours']}h initial study")
        elif args.command == "stats":
            counts = store.pipeline_counts()
            print("\n".join(f"{status}: {total}" for status, total in counts) or "No jobs saved.")
        elif args.command == "analyze-all":
            ids = store.unanalyzed_job_ids()
            for job_id in ids:
                _analyze(store, job_id, args.profile, args.provider)
                analysis = store.get_analysis(job_id)
                print(f"#{job_id}: {analysis.current_match}% -> {analysis.seven_day_match}% {analysis.recommendation}")
            print(f"Analyzed {len(ids)} new job(s).")
        elif args.command == "shortlist":
            rows = store.shortlist(args.minimum, args.limit)
            if not rows:
                print("No jobs meet the shortlist threshold.")
            for row in rows:
                print(f"\n[{row['id']}] {row['title']}\nCompany: {row['company']}\n"
                      f"Match: {row['current_match']}% -> {row['seven_day_match']}% | {row['recommendation']}\n"
                      f"Salary: {row['salary'] or 'not stated'}\nURL: {row['url'] or 'not supplied'}")
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _job_from_args(args: argparse.Namespace) -> Job:
    if args.file:
        description = Path(args.file).read_text(encoding="utf-8")
    elif args.description:
        description = args.description
    elif args.url:
        description = _fetch_job_text(args.url)
    elif not sys.stdin.isatty():
        description = sys.stdin.read()
    else:
        print("Paste job description. Finish with a line containing only END:")
        lines = []
        while (line := input()) != "END":
            lines.append(line)
        description = "\n".join(lines)
    if len(description.strip()) < 40:
        raise ValueError("Job description is too short (minimum 40 characters)")
    return Job(None, args.title, args.company, description.strip(), args.url, "manual",
               args.salary, args.remote)


def _fetch_job_text(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PersonalJobResearch/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if content_type not in ("text/html", "text/plain"):
                raise ValueError(f"Unsupported URL content type: {content_type}")
            raw = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not load URL: {exc}. Use --file or paste the description instead.") from exc
    raw = re.sub(r"(?is)<(script|style|svg|noscript).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _analyze(store: Storage, job_id: int, profile_path: str, provider: str) -> None:
    profile, job = load_profile(profile_path), store.get_job(job_id)
    if provider == "llm":
        key = os.getenv("LLM_API_KEY")
        if not key:
            raise ValueError("LLM_API_KEY is required for --provider llm")
        analyzer = OpenAICompatibleAnalyzer(key, os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
                                            os.getenv("LLM_MODEL", "gpt-5-mini"))
    else:
        analyzer = HeuristicAnalyzer()
    store.save_analysis(job_id, analyzer.analyze(job, profile))


def _show(store: Storage, job_id: int) -> None:
    job, analysis = store.get_job(job_id), store.get_analysis(job_id)
    print(f"\n[{job.id}] {job.title}\nCompany: {job.company}\nLocation mode: {job.remote_status}")
    if not analysis:
        print("Status: not analyzed"); return
    print(f"\nCURRENT MATCH: {analysis.current_match}%")
    print(f"7-DAY MATCH:   {analysis.seven_day_match}%")
    print(f"RECOMMENDATION: {analysis.recommendation}\nReason: {analysis.reason}")
    _section("Strong", analysis.strengths)
    missing = [f"{r.skill} — {r.gap_type}, ~{r.estimated_learning_hours}h" for r in analysis.requirements if r.gap_type != "KNOW"]
    _section("Missing / gaps", missing)
    _section("Learn this week", analysis.learning_tasks)
    _section("Important risks", analysis.risks)


def _section(title: str, values: list[str]) -> None:
    if values:
        print(f"\n{title}:")
        for value in values: print(f"  - {value}")


def _list(store: Storage) -> None:
    rows = store.list_jobs()
    if not rows:
        print("No jobs saved."); return
    for row in rows:
        score = "—"
        if row["analysis_json"]:
            data = json.loads(row["analysis_json"]); score = f"{data['current_match']}% -> {data['seven_day_match']}%"
        print(f"#{row['id']} | {row['status']:<8} | {score:<12} | {row['title']} | {row['company']}")


def _generate(store: Storage, job_id: int, profile_path: str, provider: str) -> None:
    job, profile = store.get_job(job_id), load_profile(profile_path)
    analysis = store.get_analysis(job_id)
    if not analysis:
        raise ValueError("Analyze the job before generating materials")
    if provider == "llm":
        key = os.getenv("LLM_API_KEY")
        if not key:
            raise ValueError("LLM_API_KEY is required for --provider llm")
        generator = OpenAICompatiblePackageGenerator(
            key, os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("LLM_MODEL", "gpt-5-mini"),
        )
    else:
        generator = HonestTemplateGenerator()
    store.save_materials(job_id, generator.generate(job, profile, analysis))


def _materials(store: Storage, job_id: int) -> None:
    package = store.get_materials(job_id)
    if not package:
        raise ValueError("No application materials; run generate first")
    print("\nPROFESSIONAL SUMMARY\n" + package.professional_summary)
    _section("CV skills order", package.cv_skills_order)
    _section("CV project bullets", package.cv_project_bullets)
    print("\nCOVER LETTER\n" + package.cover_letter)
    print("\nAPPLICATION SUMMARY\n" + package.application_summary)
    if package.common_answers:
        print("\nCOMMON ANSWERS")
        for question, answer in package.common_answers.items():
            print(f"\n{question}\n{answer}")
    _section("Risks — verify before sending", package.risks)
    _section("Interview preparation", package.interview_points)


def _export(store: Storage, job_id: int, output: str | None) -> None:
    job, package = store.get_job(job_id), store.get_materials(job_id)
    if not package:
        raise ValueError("No application materials; run approve or generate first")
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", job.title).strip("_")[:60] or "job"
    path = Path(output) if output else Path("outputs") / f"job_{job_id}_{safe_title}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    sections = [
        f"# Application package: {job.title}", f"**Company:** {job.company}",
        f"**URL:** {job.url or 'Not supplied'}", "## Professional summary",
        package.professional_summary, "## CV skills order",
        "\n".join(f"- {item}" for item in package.cv_skills_order), "## CV project bullets",
        "\n".join(f"- {item}" for item in package.cv_project_bullets), "## Cover letter",
        package.cover_letter, "## Application summary", package.application_summary,
        "## Common answers",
        "\n\n".join(f"### {question}\n\n{answer}" for question, answer in package.common_answers.items()),
        "## Risks — verify before sending", "\n".join(f"- {item}" for item in package.risks) or "- None identified",
        "## Interview preparation", "\n".join(f"- {item}" for item in package.interview_points),
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Exported: {path.resolve()}")
