"""Job feed, India-wide geo filtering, match tiers, pagination, and application tracking endpoints."""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, defer

from backend.api.deps import get_session_id, require_api_auth
from backend.db.models import JobListing
from backend.db.session import get_db
from backend.schemas.job import (
    ApplicationStateResponse,
    ApplicationUpdateRequest,
    JobListingResponse,
    JobListResponse,
    JobMatchSummary,
)
from backend.services.corpus_cache import get_corpus_cache
from backend.services.session_store import EphemeralApplication, get_session_store, score_missing_ephemeral_jobs

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"], dependencies=[Depends(require_api_auth)])

_STATUS_CANONICAL = {
    "new": "new",
    "saved": "Saved",
    "interested": "Interested",
    "reviewing": "Interested",
    "pending confirmation": "Pending Confirmation",
    "applied": "Applied",
    "assessment": "Assessment",
    "interview": "Interview",
    "interviewing": "Interview",
    "offer": "Offer",
    "selected": "Offer",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "dismissed": "Rejected",
}


def _normalize_status(value: str) -> str:
    return _STATUS_CANONICAL.get((value or "new").strip().lower(), value)


def _serialize_job(
    job,
    match,
    app_rec,
    include_description: bool = False,
    full_description: Optional[str] = None,
) -> JobListingResponse:
    match_summary = None
    if match is not None:
        match_summary = JobMatchSummary(
            match_score=match.match_score,
            semantic_score=match.semantic_score,
            skill_score=match.skill_score,
            entry_level_bonus=match.entry_level_bonus,
            eligibility_status=getattr(match, "eligibility_status", "Eligible") or "Eligible",
            matching_skills=match.matching_skills_json or [],
            missing_skills=match.missing_skills_json or [],
            recommended_improvements=getattr(match, "recommended_improvements_json", []) or [],
            explanation=match.explanation or "",
            score_breakdown=match.score_breakdown_json or {},
        )

    app_state = ApplicationStateResponse(
        status=_normalize_status(app_rec.status) if app_rec else "new",
        is_saved=app_rec.is_saved if app_rec else False,
        user_approved=app_rec.user_approved if app_rec else False,
        dismissed=getattr(app_rec, "dismissed", False) if app_rec else False,
        notes=app_rec.notes if app_rec else "",
        saved_at=getattr(app_rec, "saved_at", None) if app_rec else None,
        clicked_apply_at=getattr(app_rec, "clicked_apply_at", None) if app_rec else None,
        applied_at=app_rec.applied_at if app_rec else None,
        follow_up_date=getattr(app_rec, "follow_up_date", None) if app_rec else None,
        status_history=getattr(app_rec, "status_history_json", []) or [] if app_rec else [],
        updated_at=app_rec.updated_at if app_rec else None,
    )

    desc = (full_description if full_description is not None else getattr(job, "description", "")) if include_description else ""

    return JobListingResponse(
        id=job.id,
        source=job.source,
        company=job.company,
        company_logo_url=job.company_logo_url,
        title=job.title,
        location=job.location,
        city=job.city,
        state=getattr(job, "state", None),
        country=job.country,
        city_tier=getattr(job, "city_tier", None),
        work_mode=job.work_mode or ("remote" if job.is_remote else "unknown"),
        is_remote=job.is_remote,
        role_category=job.role_category,
        domain_tags=getattr(job, "domain_tags_json", None) or [],
        seniority_level=job.seniority_level,
        is_entry_level_priority=job.is_entry_level_priority,
        fresher_eligible=bool(getattr(job, "fresher_eligible", job.is_entry_level_priority)),
        experience_requirement=getattr(job, "experience_requirement", None),
        salary_or_stipend=getattr(job, "salary_or_stipend", None),
        employment_type=job.employment_type,
        description=desc,
        required_skills=job.required_skills_json or [],
        apply_url=job.apply_url,
        source_url=job.source_url,
        posted_at=job.posted_at,
        discovered_at=job.discovered_at,
        last_verified_at=getattr(job, "last_verified_at", None),
        verified=job.verified,
        is_expired=bool(getattr(job, "is_expired", False)),
        match=match_summary,
        application=app_state,
    )


def _in_match_tier(score: Optional[float], tier: str) -> bool:
    if tier == "all":
        return True
    if score is None:
        return False
    if tier == "90-100":
        return score >= 90.0
    if tier == "80-89":
        return 80.0 <= score < 90.0
    if tier == "70-79":
        return 70.0 <= score < 80.0
    if tier == "below-70":
        return score < 70.0
    return True


@router.get("", response_model=JobListResponse)
def list_jobs(
    role_category: Optional[str] = Query(default=None),
    seniority_level: Optional[str] = Query(default=None),
    work_mode: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    cities: Optional[str] = Query(default=None, description="Comma-separated multi-city filter"),
    state: Optional[str] = Query(default=None),
    states: Optional[str] = Query(default=None, description="Comma-separated multi-state filter"),
    city_tier: Optional[str] = Query(default=None, description="Metro | Tier-2 | All"),
    country: Optional[str] = Query(default=None),
    all_india_only: bool = Query(default=False),
    include_worldwide_remote: bool = Query(default=True),
    company: Optional[str] = Query(default=None),
    skill: Optional[str] = Query(default=None),
    employment_type: Optional[str] = Query(default=None),
    salary_only: bool = Query(default=False),
    entry_level_only: bool = Query(default=False),
    fresher_only: bool = Query(default=False),
    posted_days: Optional[int] = Query(default=None, ge=1, le=365),
    saved_only: bool = Query(default=False),
    tracked_only: bool = Query(default=False),
    hide_dismissed: bool = Query(default=True),
    status_filter: Optional[str] = Query(default=None),
    min_match: float = Query(default=0.0, ge=0.0, le=100.0),
    match_tier: str = Query(default="all", description="all | 90-100 | 80-89 | 70-79 | below-70"),
    include_closest_fallback: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    include_description: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    """List verified shared jobs from in-memory corpus cache paired with ephemeral session matches/tracker."""
    snap = get_corpus_cache().get_snapshot(db)
    sess = get_session_store().get_or_create(session_key)

    if sess.active_resume is not None and len(sess.active_matches) < len(snap.jobs_by_id):
        score_missing_ephemeral_jobs(db, sess)

    session_matches = sess.active_matches
    session_apps = sess.applications
    match_scores_by_job: dict[int, float] = {
        jid: float(m.match_score) for jid, m in session_matches.items()
    }
    app_summary_by_job = {
        jid: (_normalize_status(a.status), bool(a.is_saved), bool(getattr(a, "dismissed", False)))
        for jid, a in session_apps.items()
    }

    wm_l = work_mode.lower() if work_mode and work_mode.lower() != "all" else None
    rc_f = role_category if role_category and role_category != "All" else None
    sen_f = seniority_level if seniority_level and seniority_level != "All" else None
    city_l = city.lower() if city and city != "All" else None
    state_l = state.lower() if state and state != "All" else None
    tier_norm = None
    if city_tier and city_tier != "All":
        tier_norm = "Metro" if "metro" in city_tier.lower() else ("Tier-2" if "tier" in city_tier.lower() else city_tier)
    country_l = country.lower() if country and country != "All" else None
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=posted_days)).timestamp() if posted_days is not None else None

    matched_jobs = []
    pre_match_pool = []

    search_l = search.strip().lower() if search else None
    company_l = company.strip().lower() if company else None
    skill_l = skill.strip().lower() if skill else None
    emp_l = employment_type.strip().lower() if employment_type and employment_type != "All" else None
    status_norm = _normalize_status(status_filter) if status_filter and status_filter != "All" else None
    multi_states = {s.strip().lower() for s in (states or "").split(",") if s.strip()}
    multi_cities = {c.strip().lower() for c in (cities or "").split(",") if c.strip()}

    for job in snap.dedup_jobs:
        if wm_l and job.work_mode != wm_l:
            continue
        if rc_f and job.role_category != rc_f:
            continue
        if sen_f:
            if sen_f == "entry_level":
                if job.seniority_level not in ("entry_level", "new_grad"):
                    continue
            elif sen_f == "fresher":
                if job.seniority_level not in ("entry_level", "new_grad", "intern"):
                    continue
            elif job.seniority_level != sen_f:
                continue
        if entry_level_only and not job.is_entry_level_priority:
            continue
        if fresher_only and not job.fresher_eligible:
            continue
        if all_india_only and job.country != "India":
            continue
        if city_l and job.city_lower != city_l:
            continue
        if state_l and job.state_lower != state_l:
            continue
        if tier_norm and job.city_tier != tier_norm:
            continue
        if country_l:
            j_country_l = (job.country or "").lower()
            is_worldwide_remote_match = (
                include_worldwide_remote
                and not all_india_only
                and (wm_l == "remote" or job.work_mode == "remote")
                and j_country_l == "remote / global"
            )
            if j_country_l != country_l and not is_worldwide_remote_match:
                continue
        if salary_only and job.salary_or_stipend is None:
            continue
        if cutoff_ts is not None:
            p_ts = job.posted_at.timestamp() if job.posted_at else 0.0
            if max(p_ts, job.discovered_ts) < cutoff_ts:
                continue

        app_info = app_summary_by_job.get(job.id)
        curr_status = app_info[0] if app_info else "new"
        is_saved = app_info[1] if app_info else False
        is_dismissed = app_info[2] if app_info else False

        if hide_dismissed and is_dismissed and not saved_only and not tracked_only:
            continue
        if multi_states and job.state_lower not in multi_states:
            continue
        if multi_cities and job.city_lower not in multi_cities:
            continue
        if saved_only and not is_saved:
            continue
        if tracked_only and curr_status == "new" and not is_saved:
            continue
        if status_norm and curr_status != status_norm:
            continue

        if company_l and company_l not in job.company_lower:
            continue
        if emp_l and emp_l not in job.emp_lower:
            continue
        if skill_l and skill_l not in job.skills_joined_lower and skill_l not in job.title_lower:
            continue
        if search_l and search_l not in job.haystack_lower:
            continue

        if include_closest_fallback:
            pre_match_pool.append(job)

        score_val = match_scores_by_job.get(job.id)
        if min_match > 0.0 and (score_val is None or score_val < float(min_match)):
            continue
        if not _in_match_tier(score_val, match_tier):
            continue

        matched_jobs.append(job)

    def _job_sort_key(job):
        exact_country = 1 if (country_l and (job.country or "").lower() == country_l) else 0
        return (
            exact_country,
            match_scores_by_job.get(job.id, 0.0),
            1 if job.fresher_eligible else 0,
            job.discovered_ts,
        )

    matched_jobs.sort(key=_job_sort_key, reverse=True)

    total = len(matched_jobs)
    if limit is not None:
        safe_page = 1
        effective_page_size = limit
        total_pages = max(1, math.ceil(total / limit))
        page_jobs = matched_jobs[:limit]
    else:
        effective_page_size = page_size
        total_pages = max(1, math.ceil(total / page_size))
        safe_page = min(page, total_pages)
        start = (safe_page - 1) * page_size
        page_jobs = matched_jobs[start : start + page_size]

    closest_jobs = []
    if include_closest_fallback and not matched_jobs and pre_match_pool:
        pre_match_pool.sort(key=_job_sort_key, reverse=True)
        closest_jobs = pre_match_pool[:10]

    desc_map = {}
    if include_description and (page_jobs or closest_jobs):
        need_ids = [j.id for j in page_jobs] + [j.id for j in closest_jobs]
        desc_map = {
            jid: txt
            for jid, txt in db.query(JobListing.id, JobListing.description)
            .filter(JobListing.id.in_(need_ids))
            .all()
        }

    items = [
        _serialize_job(
            j,
            session_matches.get(j.id),
            session_apps.get(j.id),
            include_description=include_description,
            full_description=desc_map.get(j.id),
        )
        for j in page_jobs
    ]
    closest = [
        _serialize_job(
            j,
            session_matches.get(j.id),
            session_apps.get(j.id),
            include_description=include_description,
            full_description=desc_map.get(j.id),
        )
        for j in closest_jobs
    ]

    return JobListResponse(
        total=total,
        page=safe_page,
        page_size=effective_page_size,
        total_pages=total_pages,
        items=items,
        closest_matches=closest,
    )


@router.get("/{job_id}", response_model=JobListingResponse)
def get_job_detail(
    job_id: int,
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    job = db.query(JobListing).filter(JobListing.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job listing not found.")

    sess = get_session_store().get_or_create(session_key)
    if sess.active_resume is not None and job.id not in sess.active_matches:
        score_missing_ephemeral_jobs(db, sess, candidate_jobs=[job])
    return _serialize_job(
        job,
        sess.active_matches.get(job.id),
        sess.applications.get(job.id),
        include_description=True,
    )


@router.patch("/{job_id}/application", response_model=ApplicationStateResponse)
def update_application_tracking(
    job_id: int,
    payload: ApplicationUpdateRequest,
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    job = db.query(JobListing).filter(JobListing.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job listing not found.")

    sess = get_session_store().get_or_create(session_key)
    record = sess.applications.get(job_id)
    if record is None:
        record = EphemeralApplication(job_id=job_id)
        sess.applications[job_id] = record

    effective_approved = (
        payload.user_approved if payload.user_approved is not None else record.user_approved
    )
    target_status = _normalize_status(payload.status) if payload.status is not None else None

    if target_status == "Applied" and not effective_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Manual review and approval required: set user_approved=true after reviewing "
                "the official company application link."
            ),
        )

    if payload.user_approved is not None:
        record.user_approved = payload.user_approved
    if payload.dismissed is not None:
        record.dismissed = payload.dismissed
    if payload.clicked_apply:
        record.clicked_apply_at = datetime.now(timezone.utc)
        if _normalize_status(record.status) in ("new", "Saved", "Interested") and target_status is None:
            target_status = "Pending Confirmation"
    if payload.is_saved is not None:
        record.is_saved = payload.is_saved
        if payload.is_saved:
            if record.saved_at is None:
                record.saved_at = datetime.now(timezone.utc)
            if _normalize_status(record.status) == "new" and target_status is None:
                record.status = "Saved"
    if target_status is not None:
        prev_status = _normalize_status(record.status)
        if prev_status != target_status:
            history = list(record.status_history_json or [])
            history.append(
                {
                    "from": prev_status,
                    "to": target_status,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            record.status_history_json = history
        record.status = target_status
        if target_status == "Applied" and record.applied_at is None:
            record.applied_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        record.notes = payload.notes
    if payload.follow_up_date is not None:
        record.follow_up_date = payload.follow_up_date
    record.updated_at = datetime.now(timezone.utc)

    return ApplicationStateResponse(
        status=_normalize_status(record.status),
        is_saved=record.is_saved,
        user_approved=record.user_approved,
        dismissed=record.dismissed,
        notes=record.notes,
        saved_at=record.saved_at,
        clicked_apply_at=record.clicked_apply_at,
        applied_at=record.applied_at,
        follow_up_date=record.follow_up_date,
        status_history=record.status_history_json or [],
        updated_at=record.updated_at,
    )
