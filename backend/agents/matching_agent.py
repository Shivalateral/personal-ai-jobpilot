"""Job Matching Agent: batch-embeds and scores verified jobs against the active resume."""

import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.db.models import JobListing, JobMatch, Resume
from backend.db.vector_store import EmbeddingService, get_embedding_service
from backend.services.matching_engine import (
    MatchingEngine,
    build_job_profile_text,
    build_resume_profile_text,
)

logger = logging.getLogger(__name__)


class JobMatchingAgent:
    """Computes and stores explainable JobMatch records using fast batch embeddings."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        matching_engine: Optional[MatchingEngine] = None,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.matching_engine = matching_engine or MatchingEngine(embedding_service=self.embedding_service)

    def match_jobs(
        self,
        db: Session,
        resume: Optional[Resume],
        jobs: List[JobListing],
        use_llm_explanation: bool = True,
    ) -> List[Tuple[JobListing, JobMatch]]:
        """Score verified jobs against the active resume using batch embeddings."""
        if resume is None or not jobs:
            return []

        resume_emb = self.embedding_service.embed(build_resume_profile_text(resume))
        from backend.db.vector_store import get_vector_store
        cached_embs = get_vector_store().get_job_embeddings([j.id for j in jobs])
        missing_jobs = [j for j in jobs if j.id not in cached_embs]
        if missing_jobs:
            missing_embs = self.embedding_service.embed_batch([build_job_profile_text(j) for j in missing_jobs])
            for j, emb in zip(missing_jobs, missing_embs):
                cached_embs[j.id] = emb
        job_embs = [cached_embs[j.id] for j in jobs]
        existing_map = {
            m.job_id: m
            for m in db.query(JobMatch).filter(JobMatch.resume_id == resume.id).all()
        }

        results: List[Tuple[JobListing, JobMatch]] = []
        llm_budget = 8 if (use_llm_explanation and self.matching_engine.llm_client.is_available) else 0

        for idx, (job, job_emb) in enumerate(zip(jobs, job_embs)):
            should_llm = llm_budget > 0 and job.is_entry_level_priority and idx < 15
            comp = self.matching_engine.compute_match(
                resume=resume,
                job=job,
                resume_embedding=resume_emb,
                job_embedding=job_emb,
                use_llm_explanation=should_llm,
            )
            if should_llm and self.matching_engine.llm_client.is_available:
                llm_budget -= 1

            existing = existing_map.get(job.id)
            if existing:
                existing.match_score = comp.match_score
                existing.semantic_score = comp.semantic_score
                existing.skill_score = comp.skill_score
                existing.entry_level_bonus = comp.entry_level_bonus
                existing.eligibility_status = comp.eligibility_status
                existing.matching_skills_json = comp.matching_skills
                existing.missing_skills_json = comp.missing_skills
                existing.recommended_improvements_json = comp.recommended_improvements
                existing.explanation = comp.explanation
                existing.score_breakdown_json = comp.score_breakdown
                match_row = existing
            else:
                match_row = JobMatch(
                    resume_id=resume.id,
                    job_id=job.id,
                    match_score=comp.match_score,
                    semantic_score=comp.semantic_score,
                    skill_score=comp.skill_score,
                    entry_level_bonus=comp.entry_level_bonus,
                    eligibility_status=comp.eligibility_status,
                    matching_skills_json=comp.matching_skills,
                    missing_skills_json=comp.missing_skills,
                    recommended_improvements_json=comp.recommended_improvements,
                    explanation=comp.explanation,
                    score_breakdown_json=comp.score_breakdown,
                )
                db.add(match_row)
            results.append((job, match_row))

        db.commit()
        logger.info("JobMatchingAgent scored %d jobs for resume_id=%s", len(results), resume.id)
        return results
