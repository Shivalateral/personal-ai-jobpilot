"""Resume Intelligence Agent: parses, encrypts, activates, edits, and re-scores user resumes."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.core.security import ResumeVault, sha256_digest
from backend.db.models import JobListing, JobMatch, Resume
from backend.db.vector_store import VectorStore, get_vector_store
from backend.services.matching_engine import MatchingEngine, build_job_profile_text, build_resume_profile_text
from backend.services.resume_parser import ResumeParserService

logger = logging.getLogger(__name__)


class ResumeIntelligenceAgent:
    """Handles secure resume ingestion, review/edits, switching, and fast batch re-scoring."""

    def __init__(
        self,
        parser: Optional[ResumeParserService] = None,
        vault: Optional[ResumeVault] = None,
        vector_store: Optional[VectorStore] = None,
        matching_engine: Optional[MatchingEngine] = None,
    ) -> None:
        self.parser = parser or ResumeParserService()
        self.vault = vault or ResumeVault()
        self.vector_store = vector_store or get_vector_store()
        self.matching_engine = matching_engine or MatchingEngine(
            embedding_service=self.vector_store.embedding_service
        )

    def rescore_all_jobs(self, db: Session, resume: Resume) -> int:
        """Batch-embed and re-score all active verified jobs against the given resume."""
        profile_text = build_resume_profile_text(resume)
        resume_emb = self.vector_store.upsert_resume(
            resume_id=resume.id,
            document=profile_text,
            metadata={
                "resume_id": resume.id,
                "experience_level": resume.experience_level,
                "skills": ", ".join((resume.skills_json or [])[:20]),
            },
        )

        jobs = (
            db.query(JobListing)
            .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
            .all()
        )
        if not jobs:
            return 0

        job_ids = [j.id for j in jobs]
        cached_embs = self.vector_store.get_job_embeddings(job_ids)
        missing_jobs = [j for j in jobs if j.id not in cached_embs]
        if missing_jobs:
            missing_embs = self.vector_store.embedding_service.embed_batch(
                [build_job_profile_text(j) for j in missing_jobs]
            )
            for j, emb in zip(missing_jobs, missing_embs):
                cached_embs[j.id] = emb

        job_embeddings = [cached_embs[j.id] for j in jobs]
        existing_matches = {
            m.job_id: m
            for m in db.query(JobMatch).filter(JobMatch.resume_id == resume.id).all()
        }

        count = 0
        for job, job_emb in zip(jobs, job_embeddings):
            comp = self.matching_engine.compute_match(
                resume=resume,
                job=job,
                resume_embedding=resume_emb,
                job_embedding=job_emb,
                use_llm_explanation=False,
            )
            match_row = existing_matches.get(job.id)
            if match_row:
                match_row.match_score = comp.match_score
                match_row.semantic_score = comp.semantic_score
                match_row.skill_score = comp.skill_score
                match_row.entry_level_bonus = comp.entry_level_bonus
                match_row.eligibility_status = comp.eligibility_status
                match_row.matching_skills_json = comp.matching_skills
                match_row.missing_skills_json = comp.missing_skills
                match_row.recommended_improvements_json = comp.recommended_improvements
                match_row.explanation = comp.explanation
                match_row.score_breakdown_json = comp.score_breakdown
            else:
                db.add(
                    JobMatch(
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
                )
            count += 1
        return count

    def ingest_resume(
        self,
        db: Session,
        file_bytes: bytes,
        filename: str,
        rescore_existing_jobs: bool = True,
        user_id: int = 1,
    ) -> tuple[Resume, bool, int]:
        """Parse, encrypt, persist (replacing prior active resume for this user), index, and re-score."""
        parsed = self.parser.parse(file_bytes, filename)
        file_hash = sha256_digest(file_bytes)
        encrypted_raw = self.vault.encrypt(parsed.raw_text)

        existing_active = (
            db.query(Resume)
            .filter(Resume.user_id == user_id, Resume.is_active.is_(True))
            .all()
        )
        replaced_previous = len(existing_active) > 0
        for old in existing_active:
            old.is_active = False

        resume = Resume(
            user_id=user_id,
            filename=filename,
            file_type=parsed.file_type,
            file_hash=file_hash,
            encrypted_raw_text=encrypted_raw,
            candidate_name=parsed.candidate_name,
            graduation_year=parsed.graduation_year,
            summary=parsed.summary,
            skills_json=parsed.skills,
            soft_skills_json=parsed.soft_skills,
            languages_frameworks_json=parsed.languages_frameworks,
            domain_knowledge_json=parsed.domain_knowledge,
            achievements_json=parsed.achievements,
            education_json=parsed.education,
            experience_json=parsed.experience,
            projects_json=parsed.projects,
            qualifications_json=parsed.qualifications,
            target_roles_json=parsed.target_roles,
            preferred_locations_json=parsed.preferred_locations,
            keywords_json=parsed.keywords,
            experience_level=parsed.experience_level,
            is_active=True,
        )
        db.add(resume)
        db.flush()

        jobs_rescored = self.rescore_all_jobs(db, resume) if rescore_existing_jobs else 0
        db.commit()
        db.refresh(resume)
        logger.info("Ingested resume id=%s (%s), replaced=%s, rescored=%s", resume.id, resume.file_type, replaced_previous, jobs_rescored)
        return resume, replaced_previous, jobs_rescored

    def activate_resume(
        self, db: Session, resume_id: int, rescore: bool = True, user_id: int = 1
    ) -> tuple[Resume, int]:
        """Switch the active resume for the given user and optionally re-score."""
        target = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_id).first()
        if not target:
            raise ValueError("Resume not found.")
        for r in db.query(Resume).filter(Resume.user_id == user_id).all():
            r.is_active = (r.id == resume_id)
        db.flush()
        rescored = self.rescore_all_jobs(db, target) if rescore else 0
        db.commit()
        db.refresh(target)
        return target, rescored

    def update_resume_profile(
        self, db: Session, resume_id: int, updates: Dict[str, Any], user_id: int = 1
    ) -> tuple[Resume, int]:
        """Allow user review and correction of extracted resume profile fields."""
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_id).first()
        if not resume:
            raise ValueError("Resume not found.")

        field_map = {
            "candidate_name": "candidate_name",
            "graduation_year": "graduation_year",
            "summary": "summary",
            "experience_level": "experience_level",
            "skills": "skills_json",
            "soft_skills": "soft_skills_json",
            "domain_knowledge": "domain_knowledge_json",
            "target_roles": "target_roles_json",
            "preferred_locations": "preferred_locations_json",
            "keywords": "keywords_json",
            "qualifications": "qualifications_json",
        }
        for api_key, col_name in field_map.items():
            if api_key in updates and updates[api_key] is not None:
                setattr(resume, col_name, updates[api_key])

        db.flush()
        rescored = self.rescore_all_jobs(db, resume) if resume.is_active else 0
        db.commit()
        db.refresh(resume)
        return resume, rescored

    def get_active_resume(self, db: Session, user_id: int = 1) -> Optional[Resume]:
        return (
            db.query(Resume)
            .filter(Resume.user_id == user_id, Resume.is_active.is_(True))
            .order_by(Resume.created_at.desc())
            .first()
        )

    def decrypt_raw_text(self, resume: Resume) -> str:
        return self.vault.decrypt(resume.encrypted_raw_text)
