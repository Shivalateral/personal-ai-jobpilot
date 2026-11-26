"""Tests for end-to-end LangGraph discovery pipeline and APScheduler configuration."""

from backend.agents.discovery_agent import JobDiscoveryAgent
from backend.agents.pipeline_graph import DiscoveryPipelineOrchestrator
from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.db.models import JobListing, JobMatch, Notification
from backend.scheduler.daily_scheduler import DailySchedulerManager
from backend.services.discovery_sources import RawDiscoveredJob
from tests.helpers import build_sample_pdf_bytes


class _StubSourcesClient:
    def fetch_all(self):
        return (
            [
                RawDiscoveredJob(
                    source="greenhouse",
                    external_id="p-1",
                    company="DataNova",
                    title="Data Scientist Intern",
                    location="Remote",
                    description="Python, SQL, Pandas, Scikit-learn, PyTorch.",
                    apply_url="https://boards.greenhouse.io/datanova/jobs/p-1",
                    required_skills=["Python", "SQL", "Pandas", "Scikit-learn", "PyTorch"],
                    role_category="ML/Data Intern",
                    seniority_level="intern",
                    is_entry_level_priority=True,
                )
            ],
            ["greenhouse:datanova"],
        )


def test_langgraph_pipeline_end_to_end(db_session):
    ResumeIntelligenceAgent().ingest_resume(
        db=db_session,
        file_bytes=build_sample_pdf_bytes(),
        filename="alex.pdf",
        rescore_existing_jobs=False,
    )

    orchestrator = DiscoveryPipelineOrchestrator(
        discovery_agent=JobDiscoveryAgent(sources_client=_StubSourcesClient())
    )
    run = orchestrator.run(db=db_session, trigger_type="manual", verify_urls_live=False)

    assert run.status == "completed"
    assert run.total_fetched == 1
    assert run.new_verified_jobs == 1
    assert run.matches_computed == 1
    assert run.notifications_created == 1

    assert db_session.query(JobListing).count() == 1
    assert db_session.query(JobMatch).count() == 1
    assert db_session.query(Notification).count() == 1

    # Second run with same feed must deduplicate cleanly
    run2 = orchestrator.run(db=db_session, trigger_type="scheduled", verify_urls_live=False)
    assert run2.new_verified_jobs == 0
    assert run2.duplicates_skipped == 1
    assert run2.notifications_created == 0


def test_scheduler_registers_daily_cron(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    from backend.core.config import get_settings

    get_settings.cache_clear()
    mgr = DailySchedulerManager()
    mgr.start()
    status = mgr.status()
    assert status["enabled"] is True
    assert status["running"] is True
    assert status["next_run_time"] is not None
    mgr.shutdown()
    assert mgr.status()["running"] is False
