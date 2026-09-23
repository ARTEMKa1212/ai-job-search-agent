import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tempfile
import unittest
from pathlib import Path

from job_agent.analyzer import HeuristicAnalyzer
from job_agent.models import CandidateProfile, Job
from job_agent.storage import Storage
from job_agent.generator import HonestTemplateGenerator
from job_agent.cli import _export


def profile() -> CandidateProfile:
    return CandidateProfile("Test", "UK", ["UK"], True, ["Computer Science"],
                            {"Python": "KNOW", "Docker": "LEARN_FAST"},
                            ["Python API project"], 0, ["Junior Python Developer"])


class MVPTests(unittest.TestCase):
    def test_fast_learning_increases_seven_day_score(self):
        job = Job(None, "Junior Python Developer", "Acme",
                  "Remote junior role. Python and Docker are required for automation and API work.")
        analysis = HeuristicAnalyzer().analyze(job, profile())
        self.assertGreaterEqual(analysis.seven_day_match, analysis.current_match)
        self.assertTrue(any(item.skill == "Docker" and not item.blocks_application
                            for item in analysis.requirements))

    def test_storage_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "jobs.db")
            job_id = storage.add_job(Job(
                None, "Python Developer", "Acme",
                "A sufficiently long job description for testing storage.",
            ))
            job = storage.get_job(job_id)
            analysis = HeuristicAnalyzer().analyze(job, profile())
            storage.save_analysis(job_id, analysis)
            restored = storage.get_analysis(job_id)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.current_match, analysis.current_match)

    def test_application_package_is_honest(self):
        job = Job(None, "Junior Python Developer", "Acme",
                  "Remote junior Python automation role using APIs and Docker.")
        candidate = profile()
        analysis = HeuristicAnalyzer().analyze(job, candidate)
        package = HonestTemplateGenerator().generate(job, candidate, analysis)
        self.assertIn("0 years of commercial experience", package.common_answers[
            "How many years of commercial experience do you have?"
        ])
        self.assertNotIn("3 years", package.cover_letter)
        self.assertIn(candidate.name, package.cover_letter)

    def test_package_export(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "jobs.db")
            job_id = storage.add_job(Job(None, "Python Developer", "Acme",
                                         "Remote Python automation role using APIs and Docker."))
            candidate = profile()
            analysis = HeuristicAnalyzer().analyze(storage.get_job(job_id), candidate)
            storage.save_analysis(job_id, analysis)
            package = HonestTemplateGenerator().generate(storage.get_job(job_id), candidate, analysis)
            storage.save_materials(job_id, package)
            target = Path(folder) / "package.md"
            _export(storage, job_id, str(target))
            self.assertIn("## Cover letter", target.read_text(encoding="utf-8"))

    def test_duplicate_url_is_not_added_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "jobs.db")
            first = storage.add_job(Job(None, "Python", "Acme", "Long enough description for first job record.", "https://example.com/job/1"))
            second = storage.add_job(Job(None, "Python duplicate", "Acme", "Long enough duplicate description.", "https://example.com/job/1"))
            self.assertEqual(first, second)

    def test_shortlist_is_sorted_by_achievable_score(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "jobs.db")
            candidate = profile()
            for title, description in (
                ("Python Developer", "Remote junior Python automation and API developer role."),
                ("Java Architect", "Onsite senior Java architect role requiring 10 years experience."),
            ):
                job_id = storage.add_job(Job(None, title, "Acme", description))
                storage.save_analysis(job_id, HeuristicAnalyzer().analyze(storage.get_job(job_id), candidate))
            rows = storage.shortlist(minimum_score=0)
            self.assertGreaterEqual(rows[0]["seven_day_match"], rows[-1]["seven_day_match"])

    def test_expired_and_ineligible_jobs_never_enter_shortlist(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "jobs.db")
            candidate = profile()
            for status in ("EXPIRED", "INELIGIBLE"):
                job_id = storage.add_job(Job(None, "Junior Python Developer", "Acme",
                                             "Remote junior Python automation role."))
                storage.save_analysis(job_id, HeuristicAnalyzer().analyze(storage.get_job(job_id), candidate))
                storage.set_status(job_id, status)
            self.assertEqual(storage.shortlist(minimum_score=0), [])

    def test_senior_role_is_not_recommended(self):
        job = Job(None, "Senior Golang Developer", "Acme",
                  "Remote role building backend services for a global product team.")
        analysis = HeuristicAnalyzer().analyze(job, profile())
        self.assertEqual("SKIP", analysis.recommendation)
        self.assertTrue(any(item.gap_type == "EXPERIENCE_GAP" for item in analysis.requirements))

    def test_no_experience_data_role_is_prioritized(self):
        job = Job(None, "Online Data Analyst - English speaker in UK", "Acme",
                  "Remote research and evaluation tasks supporting machine learning models. "
                  "No previous professional experience is required to apply to this role. "
                  "Applicants must be resident in United Kingdom for the last 5 consecutive years.")
        candidate = profile()
        candidate.target_roles.append("Online Data Analyst")
        candidate.uk_residency_years = 5
        analysis = HeuristicAnalyzer().analyze(job, candidate)
        self.assertGreaterEqual(analysis.seven_day_match, 75)
        self.assertFalse(any("HARD FILTER" in risk for risk in analysis.risks))

    def test_residency_requirement_is_hard_filter(self):
        job = Job(None, "Online Data Analyst", "Acme",
                  "Remote entry-level work. Applicants must be resident in United Kingdom "
                  "for the last 5 consecutive years.")
        candidate = profile()
        candidate.uk_residency_years = 1
        analysis = HeuristicAnalyzer().analyze(job, candidate)
        self.assertEqual(analysis.recommendation, "SKIP")
        self.assertTrue(any("HARD FILTER" in risk for risk in analysis.risks))

    def test_unconfirmed_native_english_is_flagged(self):
        job = Job(None, "Generative AI Analyst", "Acme",
                  "Remote AI evaluation role requiring native-level fluency in English.")
        candidate = profile()
        analysis = HeuristicAnalyzer().analyze(job, candidate)
        self.assertTrue(any("USER CONFIRMATION REQUIRED" in risk for risk in analysis.risks))

    def test_advanced_backend_role_is_skipped(self):
        job = Job(None, "Backend Engineer", "Acme",
                  "Remote pivotal role. Leverage your expertise building complex platforms. "
                  "Very proficient in Node.js and JavaScript.")
        analysis = HeuristicAnalyzer().analyze(job, profile())
        self.assertEqual(analysis.recommendation, "SKIP")


if __name__ == "__main__":
    unittest.main()
