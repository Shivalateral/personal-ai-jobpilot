"""Ephemeral session-scoped resume upload, activation, review/edit, and deletion endpoints."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.api.deps import get_current_user, get_session_id, require_api_auth
from backend.db.models import JobListing, User
from backend.db.session import get_db
from backend.schemas.resume import (
    ResumeProfileResponse,
    ResumeProfileUpdateRequest,
    ResumeUploadResponse,
)
from backend.services.session_store import (
    EphemeralResume,
    get_session_store,
    ingest_ephemeral_resume,
    score_ephemeral_resume,
)

router = APIRouter(prefix="/api/v1/resume", tags=["Resume"], dependencies=[Depends(require_api_auth)])

MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB


def _to_profile_response(resume: EphemeralResume) -> ResumeProfileResponse:
    return ResumeProfileResponse(
        id=resume.id,
        filename=resume.filename,
        file_type=resume.file_type,
        candidate_name=resume.candidate_name,
        graduation_year=resume.graduation_year,
        summary=resume.summary,
        skills=resume.skills_json or [],
        soft_skills=resume.soft_skills_json or [],
        languages_frameworks=resume.languages_frameworks_json or [],
        domain_knowledge=resume.domain_knowledge_json or [],
        achievements=resume.achievements_json or [],
        education=resume.education_json or [],
        experience=resume.experience_json or [],
        projects=resume.projects_json or [],
        qualifications=resume.qualifications_json or [],
        target_roles=resume.target_roles_json or [],
        preferred_locations=resume.preferred_locations_json or [],
        keywords=resume.keywords_json or [],
        experience_level=resume.experience_level,
        is_active=resume.is_active,
        created_at=resume.created_at,
        updated_at=resume.updated_at,
    )


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_or_replace_resume(
    file: UploadFile = File(...),
    persist: bool = Query(default=False, description="Only persist encrypted resume to DB with explicit consent"),
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
    current_user: User = Depends(get_current_user),
):
    """Parse a PDF/DOCX resume for the current session; store to SQLite only when explicit consent is granted."""
    filename = file.filename or "resume.pdf"
    lower = filename.lower()
    if not (lower.endswith(".pdf") or lower.endswith(".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume exceeds the 10 MB size limit.",
        )

    sess = get_session_store().get_or_create(session_key)
    try:
        resume, replaced, rescored = ingest_ephemeral_resume(
            db=db,
            session_data=sess,
            file_bytes=content,
            filename=filename,
        )
        if persist:
            ResumeIntelligenceAgent().ingest_resume(
                db=db,
                file_bytes=content,
                filename=filename,
                rescore_existing_jobs=False,
                user_id=current_user.id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ResumeUploadResponse(
        message="Resume processed for this session and jobs scored."
        if not replaced
        else "Resume replaced for this session and jobs re-scored.",
        replaced_previous=replaced,
        profile=_to_profile_response(resume),
        jobs_rescored=rescored,
    )


@router.get("/active", response_model=ResumeProfileResponse)
def get_active_resume(session_key: str = Depends(get_session_id)):
    """Return the active resume uploaded in the current ephemeral session."""
    sess = get_session_store().get_or_create(session_key)
    resume = sess.active_resume
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume uploaded in this session yet.",
        )
    return _to_profile_response(resume)


@router.post("/{resume_id}/activate", response_model=ResumeUploadResponse)
def activate_existing_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    """Switch active resume among uploads in the current session."""
    sess = get_session_store().get_or_create(session_key)
    target = next((r for r in sess.resumes if r.id == resume_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found in this session.")
    for r in sess.resumes:
        r.is_active = r.id == resume_id
    target.updated_at = datetime.now(timezone.utc)
    rescored = score_ephemeral_resume(db, sess, target)
    return ResumeUploadResponse(
        message=f"Activated session resume #{target.id} ({target.filename}) and re-scored jobs.",
        replaced_previous=True,
        profile=_to_profile_response(target),
        jobs_rescored=rescored,
    )


@router.patch("/{resume_id}", response_model=ResumeUploadResponse)
def update_resume_profile(
    resume_id: int,
    payload: ResumeProfileUpdateRequest,
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    """Review and correct extracted resume profile details for the current session."""
    sess = get_session_store().get_or_create(session_key)
    target = next((r for r in sess.resumes if r.id == resume_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found in this session.")

    updates = payload.model_dump(exclude_unset=True)
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
    for req_key, attr in field_map.items():
        if req_key in updates and updates[req_key] is not None:
            setattr(target, attr, updates[req_key])
    target.updated_at = datetime.now(timezone.utc)
    rescored = score_ephemeral_resume(db, sess, target)
    return ResumeUploadResponse(
        message="Session resume profile updated and jobs re-scored.",
        replaced_previous=False,
        profile=_to_profile_response(target),
        jobs_rescored=rescored,
    )


@router.get("/history", response_model=List[ResumeProfileResponse])
def list_resume_history(session_key: str = Depends(get_session_id)):
    """List resumes uploaded during the current ephemeral session (newest first)."""
    sess = get_session_store().get_or_create(session_key)
    return [_to_profile_response(r) for r in reversed(sess.resumes)]


@router.delete("/{resume_id}", status_code=status.HTTP_200_OK)
def delete_resume(resume_id: int, session_key: str = Depends(get_session_id)):
    """Delete an ephemeral resume and its computed match scores from the current session."""
    sess = get_session_store().get_or_create(session_key)
    before = len(sess.resumes)
    sess.resumes = [r for r in sess.resumes if r.id != resume_id]
    if len(sess.resumes) == before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found in this session.")
    sess.matches_by_resume.pop(resume_id, None)
    return {"deleted": True, "resume_id": resume_id}


@router.get("/utilization")
def get_resume_utilization(
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
) -> Dict[str, Any]:
    """Compute real Resume Utilization analytics across matched verified jobs (no invented scores)."""
    sess = get_session_store().get_or_create(session_key)
    resume = sess.active_resume
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload a resume first to view Resume Utilization insights.",
        )

    matches = sess.active_matches
    job_rows = (
        db.query(JobListing.id, JobListing.role_category)
        .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
        .all()
    )
    cat_by_id = {jid: cat for jid, cat in job_rows}

    matched_counter: Counter = Counter()
    missing_counter: Counter = Counter()
    eligibility_counts: Counter = Counter()
    cat_scores: Dict[str, List[float]] = defaultdict(list)
    all_scores: List[float] = []

    for jid, m in matches.items():
        all_scores.append(float(m.match_score))
        eligibility_counts[m.eligibility_status or "Eligible"] += 1
        for sk in (m.matching_skills_json or []):
            matched_counter[sk] += 1
        for msk in (m.missing_skills_json or []):
            missing_counter[msk] += 1
        cat = cat_by_id.get(jid)
        if cat:
            cat_scores[cat].append(float(m.match_score))

    total = max(1, len(all_scores))
    top_matching = [
        {"skill": s, "count": c, "frequency_pct": round((c / total) * 100.0, 1)}
        for s, c in matched_counter.most_common(12)
    ]
    top_missing = [
        {"skill": s, "count": c, "demand_pct": round((c / total) * 100.0, 1)}
        for s, c in missing_counter.most_common(12)
    ]
    relevant_categories = sorted(
        [
            {
                "category": cat,
                "jobs_count": len(vals),
                "avg_match": round(sum(vals) / len(vals), 1),
                "max_match": round(max(vals), 1),
            }
            for cat, vals in cat_scores.items()
        ],
        key=lambda x: (x["avg_match"], x["jobs_count"]),
        reverse=True,
    )

    strengths = []
    if top_matching:
        strengths.append(
            f"Strongest recurring skills across live roles: {', '.join(x['skill'] for x in top_matching[:5])}."
        )
    if relevant_categories:
        best_cat = relevant_categories[0]
        strengths.append(
            f"Highest domain alignment is in {best_cat['category']} ({best_cat['avg_match']}% avg, peak {best_cat['max_match']}%)."
        )

    recommendations = []
    if top_missing:
        recommendations.append(
            f"Adding verified project/work evidence for {', '.join(x['skill'] for x in top_missing[:5])} can raise scores across high-demand listings."
        )
    unused_skills = [
        s for s in (resume.skills_json or []) if matched_counter.get(s, 0) == 0
    ]
    if unused_skills:
        recommendations.append(
            f"Profile skills rarely requested in current job listings: {', '.join(unused_skills[:6])}."
        )

    return {
        "resume_filename": resume.filename,
        "total_jobs_analyzed": len(all_scores),
        "avg_compatibility": round(sum(all_scores) / total, 1) if all_scores else 0.0,
        "max_compatibility": round(max(all_scores), 1) if all_scores else 0.0,
        "most_requested_matching_skills": top_matching,
        "missing_skills_gap": top_missing,
        "unused_resume_skills": unused_skills[:12],
        "relevant_categories": relevant_categories[:10],
        "eligibility_breakdown": dict(eligibility_counts),
        "strengths": strengths,
        "recommended_improvements": recommendations,
    }
