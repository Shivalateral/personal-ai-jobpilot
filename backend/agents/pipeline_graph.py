"""LangGraph StateGraph orchestrating autonomous daily job discovery, verification, matching, and notifications."""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from backend.agents.discovery_agent import JobDiscoveryAgent
from backend.agents.matching_agent import JobMatchingAgent
from backend.agents.notification_agent import NotificationAgent
from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.agents.verification_agent import JobVerificationAgent
from backend.db.models import DiscoveryRun, JobListing, JobMatch, Notification, Resume
from backend.services.corpus_cache import get_corpus_cache
from backend.services.discovery_sources import RawDiscoveredJob

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    trigger_type: str
    verify_urls_live: bool
    sources_checked: List[str]
    raw_jobs: List[RawDiscoveredJob]
    persisted_jobs: List[JobListing]
    duplicates_skipped: int
    rejected_unverified: int
    active_resume: Optional[Resume]
    matched_pairs: List[Tuple[JobListing, JobMatch]]
    notifications: List[Notification]
    error: Optional[str]


class DiscoveryPipelineOrchestrator:
    """Runs the multi-agent LangGraph pipeline and records DiscoveryRun telemetry."""

    def __init__(
        self,
        discovery_agent: Optional[JobDiscoveryAgent] = None,
        verification_agent: Optional[JobVerificationAgent] = None,
        matching_agent: Optional[JobMatchingAgent] = None,
        notification_agent: Optional[NotificationAgent] = None,
        resume_agent: Optional[ResumeIntelligenceAgent] = None,
    ) -> None:
        self.discovery_agent = discovery_agent or JobDiscoveryAgent()
        self.verification_agent = verification_agent or JobVerificationAgent()
        self.matching_agent = matching_agent or JobMatchingAgent(
            embedding_service=self.verification_agent.vector_store.embedding_service
        )
        self.notification_agent = notification_agent or NotificationAgent()
        self.resume_agent = resume_agent or ResumeIntelligenceAgent(
            vector_store=self.verification_agent.vector_store,
            matching_engine=self.matching_agent.matching_engine,
        )

    def _build_graph(self, db: Session):
        def node_discover(state: PipelineState) -> PipelineState:
            raw_jobs, sources = self.discovery_agent.discover()
            return {"raw_jobs": raw_jobs, "sources_checked": sources}

        def node_verify(state: PipelineState) -> PipelineState:
            persisted, dupes, rejected = self.verification_agent.verify_and_persist(
                db=db,
                raw_jobs=state.get("raw_jobs", []),
                verify_urls_live=state.get("verify_urls_live", False),
            )
            if persisted:
                get_corpus_cache().invalidate()
            return {
                "persisted_jobs": persisted,
                "duplicates_skipped": dupes,
                "rejected_unverified": rejected,
            }

        def node_match(state: PipelineState) -> PipelineState:
            active_resumes_all = (
                db.query(Resume)
                .filter(Resume.is_active.is_(True))
                .order_by(Resume.created_at.desc())
                .all()
            )
            # Keep newest active resume per user_id so every user workspace stays scored
            seen_users = set()
            active_resumes: List[Resume] = []
            for res in active_resumes_all:
                uid = getattr(res, "user_id", 1) or 1
                if uid not in seen_users:
                    seen_users.add(uid)
                    active_resumes.append(res)

            new_jobs = state.get("persisted_jobs", [])
            if not active_resumes:
                return {"matched_pairs": []}

            active_verified_jobs = (
                db.query(JobListing)
                .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True))
                .all()
            )
            new_jobs_by_id = {j.id: j for j in new_jobs}

            all_matched_pairs: List[Tuple[JobListing, JobMatch]] = []
            for resume in active_resumes:
                existing_matched_ids = {
                    row[0]
                    for row in db.query(JobMatch.job_id).filter(JobMatch.resume_id == resume.id).all()
                }
                jobs_to_match = list(new_jobs)
                seen_ids = set(new_jobs_by_id.keys())
                for j in active_verified_jobs:
                    if j.id not in seen_ids and j.id not in existing_matched_ids:
                        jobs_to_match.append(j)
                if jobs_to_match:
                    pairs = self.matching_agent.match_jobs(db=db, resume=resume, jobs=jobs_to_match)
                    all_matched_pairs.extend(pairs)

            return {"matched_pairs": all_matched_pairs}

        def node_notify(state: PipelineState) -> PipelineState:
            # Notify only for newly persisted high-matching jobs from this run
            new_ids = {j.id for j in state.get("persisted_jobs", [])}
            new_pairs = [pair for pair in state.get("matched_pairs", []) if pair[0].id in new_ids]
            notifications = self.notification_agent.notify_matches(db=db, matched_pairs=new_pairs)
            return {"notifications": notifications}

        graph = StateGraph(PipelineState)
        graph.add_node("discover", node_discover)
        graph.add_node("verify", node_verify)
        graph.add_node("match", node_match)
        graph.add_node("notify", node_notify)

        graph.set_entry_point("discover")
        graph.add_edge("discover", "verify")
        graph.add_edge("verify", "match")
        graph.add_edge("match", "notify")
        graph.add_edge("notify", END)

        return graph.compile()

    def run(
        self,
        db: Session,
        trigger_type: str = "manual",
        verify_urls_live: bool = False,
        existing_run_id: Optional[int] = None,
    ) -> DiscoveryRun:
        """Execute the full LangGraph pipeline and persist a DiscoveryRun audit record."""
        run_record: Optional[DiscoveryRun] = None
        if existing_run_id is not None:
            run_record = db.query(DiscoveryRun).filter(DiscoveryRun.id == existing_run_id).first()
        if run_record is None:
            run_record = DiscoveryRun(
                trigger_type=trigger_type,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(run_record)
            db.commit()
            db.refresh(run_record)

        try:
            compiled = self._build_graph(db)
            final_state: Dict[str, Any] = compiled.invoke(
                {
                    "trigger_type": trigger_type,
                    "verify_urls_live": verify_urls_live,
                }
            )
            run_record.status = "completed"
            run_record.sources_checked_json = final_state.get("sources_checked", [])
            run_record.total_fetched = len(final_state.get("raw_jobs", []))
            run_record.new_verified_jobs = len(final_state.get("persisted_jobs", []))
            run_record.duplicates_skipped = final_state.get("duplicates_skipped", 0)
            run_record.rejected_unverified = final_state.get("rejected_unverified", 0)
            run_record.matches_computed = len(final_state.get("matched_pairs", []))
            run_record.notifications_created = len(final_state.get("notifications", []))
            run_record.finished_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("Discovery pipeline failed: %s", exc)
            run_record.status = "failed"
            run_record.error_message = str(exc)
            run_record.finished_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run_record)
        return run_record
