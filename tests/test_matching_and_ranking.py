"""Tests for explainable matching, skill gap identification, and entry-level prioritization."""

from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.agents.verification_agent import JobVerificationAgent
from backend.services.discovery_sources import RawDiscoveredJob
from backend.services.matching_engine import MatchingEngine
from tests.helpers import build_sample_pdf_bytes


def test_matching_prioritizes_entry_level_and_explains_gaps(db_session):
    resume_agent = ResumeIntelligenceAgent()
    resume, _, _ = resume_agent.ingest_resume(
        db=db_session,
        file_bytes=build_sample_pdf_bytes(),
        filename="alex.pdf",
        rescore_existing_jobs=False,
    )

    verifier = JobVerificationAgent()
    jobs, _, _ = verifier.verify_and_persist(
        db_session,
        [
            RawDiscoveredJob(
                source="greenhouse",
                external_id="entry-1",
                company="VectorAI",
                title="AI/ML Engineer (New Grad)",
                location="Remote",
                description="Looking for Python, SQL, PyTorch, FastAPI, Docker, and Kubernetes.",
                apply_url="https://boards.greenhouse.io/vectorai/jobs/entry-1",
                required_skills=["Python", "SQL", "PyTorch", "FastAPI", "Docker", "Kubernetes"],
                role_category="AI/ML Engineer",
                seniority_level="new_grad",
                is_entry_level_priority=True,
            ),
            RawDiscoveredJob(
                source="lever",
                external_id="senior-1",
                company="LegacyCorp",
                title="Senior Staff ML Architect",
                location="NYC",
                description="10+ years of experience with Spark, Airflow, Snowflake, Kubernetes.",
                apply_url="https://jobs.lever.co/legacycorp/senior-1",
                required_skills=["Apache Spark", "Airflow", "Snowflake", "Kubernetes"],
                role_category="AI/ML Engineer",
                seniority_level="senior",
                is_entry_level_priority=False,
            ),
        ],
    )

    engine = MatchingEngine()
    entry_match = engine.compute_match(resume, jobs[0], use_llm_explanation=False)
    senior_match = engine.compute_match(resume, jobs[1], use_llm_explanation=False)

    assert entry_match.match_score > senior_match.match_score
    assert entry_match.entry_level_bonus > 0
    assert senior_match.entry_level_bonus < 0
    assert "Python" in entry_match.matching_skills
    assert "Kubernetes" in entry_match.missing_skills
    assert "VectorAI" in entry_match.explanation
