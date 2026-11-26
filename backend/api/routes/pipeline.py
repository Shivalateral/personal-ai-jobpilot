"""Discovery pipeline triggers (sync/background), link expiry checks, and sources metadata."""

import threading
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.agents.pipeline_graph import DiscoveryPipelineOrchestrator
from backend.agents.verification_agent import JobVerificationAgent
from backend.api.deps import require_api_auth, require_scheduler_auth
from backend.core.config import get_settings
from backend.db.models import DiscoveryRun
from backend.db.session import get_db, session_scope
from backend.scheduler.daily_scheduler import scheduler_manager
from backend.schemas.pipeline import (
    DiscoveryRunRequest,
    DiscoveryRunResponse,
    SchedulerStatusResponse,
)

router = APIRouter(tags=["Pipeline & Automation"])

_PIPELINE_LOCK = threading.Lock()


def _to_run_response(run: DiscoveryRun) -> DiscoveryRunResponse:
    return DiscoveryRunResponse(
        id=run.id,
        trigger_type=run.trigger_type,
        status=run.status,
        sources_checked=run.sources_checked_json or [],
        total_fetched=run.total_fetched,
        new_verified_jobs=run.new_verified_jobs,
        duplicates_skipped=run.duplicates_skipped,
        rejected_unverified=run.rejected_unverified,
        matches_computed=run.matches_computed,
        notifications_created=run.notifications_created,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _run_pipeline_bg(run_id: int, trigger_type: str, verify_urls_live: bool) -> None:
    if not _PIPELINE_LOCK.acquire(blocking=False):
        return
    try:
        with session_scope() as db:
            DiscoveryPipelineOrchestrator().run(
                db=db,
                trigger_type=trigger_type,
                verify_urls_live=verify_urls_live,
                existing_run_id=run_id,
            )
    finally:
        _PIPELINE_LOCK.release()


@router.post(
    "/api/v1/pipeline/run",
    response_model=DiscoveryRunResponse,
    dependencies=[Depends(require_api_auth)],
)
def trigger_discovery_pipeline(
    payload: DiscoveryRunRequest = DiscoveryRunRequest(),
    background: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Trigger the discovery pipeline synchronously or in a daemon thread (preventing duplicates)."""
    running = db.query(DiscoveryRun).filter(DiscoveryRun.status == "running").order_by(DiscoveryRun.started_at.desc()).first()
    if running and _PIPELINE_LOCK.locked():
        return _to_run_response(running)

    if background:
        placeholder = DiscoveryRun(trigger_type=payload.trigger_type, status="running")
        db.add(placeholder)
        db.commit()
        db.refresh(placeholder)
        threading.Thread(
            target=_run_pipeline_bg,
            args=(placeholder.id, payload.trigger_type, payload.verify_urls_live),
            daemon=True,
        ).start()
        return _to_run_response(placeholder)

    with _PIPELINE_LOCK:
        run = DiscoveryPipelineOrchestrator().run(
            db=db,
            trigger_type=payload.trigger_type,
            verify_urls_live=payload.verify_urls_live,
        )
    return _to_run_response(run)


@router.post(
    "/api/v1/pipeline/verify-links",
    dependencies=[Depends(require_api_auth)],
)
def verify_existing_job_links(limit: int = Query(default=25, ge=1, le=100), db: Session = Depends(get_db)):
    """Check stored job application URLs for HTTP 404/410 and mark expired listings."""
    expired = JobVerificationAgent().check_expired_links(db=db, limit=limit)
    return {"checked_limit": limit, "expired_detected": expired}


@router.post(
    "/api/v1/scheduler/run",
    response_model=DiscoveryRunResponse,
    dependencies=[Depends(require_scheduler_auth)],
)
def cloud_scheduler_webhook(db: Session = Depends(get_db)):
    """HTTP webhook endpoint for scheduled triggers."""
    with _PIPELINE_LOCK:
        run = DiscoveryPipelineOrchestrator().run(db=db, trigger_type="cloud_scheduler", verify_urls_live=False)
    return _to_run_response(run)


@router.get(
    "/api/v1/pipeline/runs",
    response_model=List[DiscoveryRunResponse],
    dependencies=[Depends(require_api_auth)],
)
def list_pipeline_runs(db: Session = Depends(get_db)):
    runs = db.query(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(30).all()
    return [_to_run_response(r) for r in runs]


@router.get(
    "/api/v1/scheduler/status",
    response_model=SchedulerStatusResponse,
    dependencies=[Depends(require_api_auth)],
)
def get_scheduler_status():
    return SchedulerStatusResponse(**scheduler_manager.status())


@router.get(
    "/api/v1/pipeline/sources",
    dependencies=[Depends(require_api_auth)],
)
def get_configured_sources():
    settings = get_settings()
    return {
        "greenhouse_boards": settings.greenhouse_board_list,
        "lever_companies": settings.lever_company_list,
        "ashby_companies": settings.ashby_company_list,
        "smartrecruiters_companies": settings.smartrecruiters_company_list,
        "workday_endpoints": settings.workday_endpoint_list,
        "enable_remotive_api": settings.enable_remotive_api,
        "enable_arbeitnow_api": settings.enable_arbeitnow_api,
        "enable_jobicy_api": settings.enable_jobicy_api,
        "enable_himalayas_api": settings.enable_himalayas_api,
        "enable_remoteok_api": settings.enable_remoteok_api,
        "adzuna_configured": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "rss_feeds": settings.rss_feed_list,
        "career_pages": settings.career_page_list,
        "compliance": {
            "unauthorized_scraping_blocked": True,
            "robots_txt_enforced": True,
            "auto_apply_disabled": True,
        },
    }
