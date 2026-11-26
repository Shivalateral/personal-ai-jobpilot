"""Thread-safe ephemeral in-memory session store for stateless multi-user isolation.

All user-specific state (uploaded resume, match predictions, saved/applied tracking,
alerts, and chat messages) lives strictly in server memory for the active browser
session (`X-Session-Id`) and is permanently discarded on logout or idle TTL expiry.
The shared verified `JobListing` repository in SQLite remains read-only per user session.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, defer

from backend.core.config import get_settings
from backend.core.security import sha256_digest
from backend.db.models import JobListing
from backend.db.vector_store import VectorStore, get_vector_store
from backend.services.corpus_cache import get_corpus_cache
from backend.services.matching_engine import (
    MatchingEngine,
    _tokenize_domain_terms,
    build_job_profile_text,
    build_resume_profile_text,
)
from backend.services.resume_parser import ResumeParserService

logger = logging.getLogger(__name__)


@dataclass
class EphemeralResume:
    id: int
    filename: str
    file_type: str
    file_hash: str
    raw_text: str
    candidate_name: Optional[str]
    graduation_year: Optional[int]
    summary: str
    skills_json: List[str] = field(default_factory=list)
    soft_skills_json: List[str] = field(default_factory=list)
    languages_frameworks_json: List[str] = field(default_factory=list)
    domain_knowledge_json: List[str] = field(default_factory=list)
    achievements_json: List[str] = field(default_factory=list)
    education_json: List[Dict[str, Any]] = field(default_factory=list)
    experience_json: List[Dict[str, Any]] = field(default_factory=list)
    projects_json: List[Dict[str, Any]] = field(default_factory=list)
    qualifications_json: List[str] = field(default_factory=list)
    target_roles_json: List[str] = field(default_factory=list)
    preferred_locations_json: List[str] = field(default_factory=list)
    keywords_json: List[str] = field(default_factory=list)
    experience_level: str = "entry_level"
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EphemeralMatch:
    resume_id: int
    job_id: int
    match_score: float
    semantic_score: float
    skill_score: float
    entry_level_bonus: float
    eligibility_status: str
    matching_skills_json: List[str] = field(default_factory=list)
    missing_skills_json: List[str] = field(default_factory=list)
    recommended_improvements_json: List[str] = field(default_factory=list)
    explanation: str = ""
    score_breakdown_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EphemeralApplication:
    job_id: int
    status: str = "new"
    is_saved: bool = False
    user_approved: bool = False
    dismissed: bool = False
    notes: str = ""
    saved_at: Optional[datetime] = None
    clicked_apply_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    follow_up_date: Optional[datetime] = None
    status_history_json: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EphemeralNotification:
    id: int
    job_id: Optional[int]
    title: str
    message: str
    match_score: float
    channel: str = "dashboard"
    is_read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EphemeralChatMessage:
    id: int
    session_id: str
    role: str
    content: str
    referenced_job_ids_json: List[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EphemeralSessionData:
    session_key: str
    last_accessed: float = field(default_factory=time.time)
    resumes: List[EphemeralResume] = field(default_factory=list)
    matches_by_resume: Dict[int, Dict[int, EphemeralMatch]] = field(default_factory=dict)
    applications: Dict[int, EphemeralApplication] = field(default_factory=dict)
    notifications: List[EphemeralNotification] = field(default_factory=list)
    chat_messages: List[EphemeralChatMessage] = field(default_factory=list)
    _next_resume_id: int = 1
    _next_notif_id: int = 1
    _next_chat_id: int = 1

    @property
    def active_resume(self) -> Optional[EphemeralResume]:
        for r in reversed(self.resumes):
            if r.is_active:
                return r
        return None

    @property
    def active_matches(self) -> Dict[int, EphemeralMatch]:
        res = self.active_resume
        if not res:
            return {}
        return self.matches_by_resume.get(res.id, {})


class EphemeralSessionStore:
    """Thread-safe RAM-only store isolating temporary user sessions with automatic TTL cleanup."""

    def __init__(self, ttl_seconds: int = 7200) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, EphemeralSessionData] = {}
        self.ttl_seconds = ttl_seconds

    def _prune_expired_locked(self) -> None:
        now = time.time()
        expired = [k for k, v in self._sessions.items() if (now - v.last_accessed) > self.ttl_seconds]
        for k in expired:
            del self._sessions[k]

    def get_or_create(self, session_key: str) -> EphemeralSessionData:
        with self._lock:
            self._prune_expired_locked()
            sess = self._sessions.get(session_key)
            if sess is None:
                sess = EphemeralSessionData(session_key=session_key)
                self._sessions[session_key] = sess
            sess.last_accessed = time.time()
            return sess

    def clear_session(self, session_key: str) -> bool:
        with self._lock:
            existed = session_key in self._sessions
            if existed:
                del self._sessions[session_key]
            return existed

    def reset_all(self) -> None:
        with self._lock:
            self._sessions.clear()

    def active_count(self) -> int:
        with self._lock:
            self._prune_expired_locked()
            return len(self._sessions)


_SESSION_STORE = EphemeralSessionStore()


def get_session_store() -> EphemeralSessionStore:
    return _SESSION_STORE


def score_ephemeral_resume(
    db: Session,
    session_data: EphemeralSessionData,
    resume: EphemeralResume,
    vector_store: Optional[VectorStore] = None,
) -> int:
    """Vectorized NumPy + pre-tokenized in-memory match scoring across the entire shared verified job corpus."""
    import numpy as np

    snap = get_corpus_cache().get_snapshot(db)
    jobs = snap.jobs
    if not jobs:
        session_data.matches_by_resume[resume.id] = {}
        return 0

    vs = vector_store or get_vector_store()
    engine = MatchingEngine(embedding_service=vs.embedding_service)
    profile_text = build_resume_profile_text(resume)
    resume_emb_list = vs.embedding_service.embed(profile_text)
    res_vec = np.asarray(resume_emb_list, dtype=np.float32)
    r_norm = float(np.linalg.norm(res_vec))
    if r_norm > 0:
        res_vec = res_vec / r_norm

    # Single vectorized BLAS dot product for all 8,000+ jobs (~1 ms)
    cosines_arr = (
        (snap.emb_matrix @ res_vec).tolist()
        if snap.emb_matrix is not None and len(snap.emb_matrix) > 0
        else []
    )
    cosines_by_id = {
        jid: max(0.0, min(1.0, float(cosines_arr[row_idx])))
        for jid, row_idx in snap.id_to_row.items()
        if row_idx < len(cosines_arr)
    }

    resume_all_skills = list(
        dict.fromkeys(
            s.strip()
            for s in (
                (resume.skills_json or [])
                + (getattr(resume, "languages_frameworks_json", None) or [])
                + (getattr(resume, "soft_skills_json", None) or [])
                + (getattr(resume, "keywords_json", None) or [])
            )
            if s and s.strip()
        )
    )
    resume_skills_lower = {s.lower() for s in resume_all_skills}
    resume_text_lower = f"{profile_text}\n{getattr(resume, 'raw_text', '') or ''}".lower()
    resume_domains = " ".join(getattr(resume, "domain_knowledge_json", None) or []).lower()
    target_roles = [r.lower() for r in (resume.target_roles_json or [])]
    pref_locs = [p.lower() for p in (resume.preferred_locations_json or ["india", "remote"])]
    is_candidate_entry = resume.experience_level in ("intern", "fresh_grad", "entry_level")
    res_tokens = _tokenize_domain_terms(
        f"{' '.join(resume_all_skills)} {' '.join(resume.target_roles_json or [])} "
        f"{resume_domains} {resume.summary or ''}"
    )

    matches_map: Dict[int, EphemeralMatch] = {}
    for job in jobs:
        cos_val = cosines_by_id.get(job.id, 0.0)
        comp = engine.compute_match_precomputed(
            resume=resume,
            job_item=job,
            semantic_cosine=cos_val,
            resume_all_skills=resume_all_skills,
            resume_skills_lower=resume_skills_lower,
            resume_text_lower=resume_text_lower,
            res_tokens=res_tokens,
            resume_domains=resume_domains,
            target_roles=target_roles,
            pref_locs=pref_locs,
            is_candidate_entry=is_candidate_entry,
            idf_weights=snap.idf_weights,
        )
        matches_map[job.id] = EphemeralMatch(
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

    session_data.matches_by_resume[resume.id] = matches_map

    notify_threshold = get_settings().discovery_min_match_notify
    existing_notif_jids = {n.job_id for n in session_data.notifications if n.job_id is not None}
    sorted_matches = sorted(
        [(job, m) for job in jobs if (m := matches_map.get(job.id)) and m.match_score >= notify_threshold],
        key=lambda pair: pair[1].match_score,
        reverse=True,
    )
    for job, m in sorted_matches[:5]:
        if job.id in existing_notif_jids:
            continue
        session_data.notifications.append(
            EphemeralNotification(
                id=session_data._next_notif_id,
                job_id=job.id,
                title=f"High Match ({m.match_score:.1f}%): {job.title} at {job.company}",
                message=(
                    f"{job.location} ({job.work_mode}) · Skills matched: "
                    f"{', '.join(m.matching_skills_json[:5]) or 'Profile overlap'}"
                ),
                match_score=m.match_score,
            )
        )
        session_data._next_notif_id += 1

    return len(matches_map)


def score_missing_ephemeral_jobs(
    db: Session,
    session_data: EphemeralSessionData,
    candidate_jobs: Optional[List[JobListing]] = None,
    vector_store: Optional[VectorStore] = None,
) -> int:
    """Lazily score only verified jobs not yet present in the active ephemeral session's match map."""
    resume = session_data.active_resume
    if resume is None:
        return 0
    existing = session_data.matches_by_resume.setdefault(resume.id, {})
    if candidate_jobs is None:
        all_rows = (
            db.query(JobListing)
            .options(defer(JobListing.description))
            .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
            .all()
        )
    else:
        all_rows = candidate_jobs
    missing = [j for j in all_rows if j.id not in existing]
    if not missing:
        return 0

    vs = vector_store or get_vector_store()
    engine = MatchingEngine(embedding_service=vs.embedding_service)
    resume_emb = vs.embedding_service.embed(build_resume_profile_text(resume))
    cached_embs = vs.get_job_embeddings([j.id for j in missing])
    unembedded_ids = [j.id for j in missing if j.id not in cached_embs]
    if unembedded_ids:
        for j, emb in zip(
            db.query(JobListing).filter(JobListing.id.in_(unembedded_ids)).all(),
            vs.embedding_service.embed_batch(
                [build_job_profile_text(x) for x in db.query(JobListing).filter(JobListing.id.in_(unembedded_ids)).all()]
            ),
        ):
            cached_embs[j.id] = emb

    notify_threshold = get_settings().discovery_min_match_notify
    existing_notif_jids = {n.job_id for n in session_data.notifications if n.job_id is not None}
    added = 0
    for job in missing:
        job_emb = cached_embs.get(job.id)
        if not job_emb:
            continue
        comp = engine.compute_match(
            resume=resume,
            job=job,
            resume_embedding=resume_emb,
            job_embedding=job_emb,
            use_llm_explanation=False,
        )
        m = EphemeralMatch(
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
        existing[job.id] = m
        added += 1
        if m.match_score >= notify_threshold and job.id not in existing_notif_jids:
            session_data.notifications.append(
                EphemeralNotification(
                    id=session_data._next_notif_id,
                    job_id=job.id,
                    title=f"High Match ({m.match_score:.1f}%): {job.title} at {job.company}",
                    message=(
                        f"{job.location} ({job.work_mode}) · Skills matched: "
                        f"{', '.join(m.matching_skills_json[:5]) or 'Profile overlap'}"
                    ),
                    match_score=m.match_score,
                )
            )
            session_data._next_notif_id += 1
            existing_notif_jids.add(job.id)
    return added


def ingest_ephemeral_resume(
    db: Session,
    session_data: EphemeralSessionData,
    file_bytes: bytes,
    filename: str,
) -> tuple[EphemeralResume, bool, int]:
    """Parse uploaded PDF/DOCX resume in RAM and score against shared jobs without DB persistence."""
    parsed = ResumeParserService().parse(file_bytes, filename)
    replaced = any(r.is_active for r in session_data.resumes)
    for r in session_data.resumes:
        r.is_active = False

    now = datetime.now(timezone.utc)
    resume = EphemeralResume(
        id=session_data._next_resume_id,
        filename=filename,
        file_type=parsed.file_type,
        file_hash=sha256_digest(file_bytes),
        raw_text=parsed.raw_text,
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
        created_at=now,
        updated_at=now,
    )
    session_data._next_resume_id += 1
    session_data.resumes.append(resume)

    rescored = score_ephemeral_resume(db, session_data, resume)
    return resume, replaced, rescored
