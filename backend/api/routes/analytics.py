"""Analytics & overview metrics reading shared in-memory corpus cache and ephemeral session state."""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_session_id, require_api_auth
from backend.db.models import DiscoveryRun
from backend.db.session import get_db
from backend.services.corpus_cache import get_corpus_cache
from backend.services.session_store import get_session_store, score_missing_ephemeral_jobs

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"], dependencies=[Depends(require_api_auth)])


@router.get("/overview")
def get_overview_analytics(
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    snap = get_corpus_cache().get_snapshot(db)
    sess = get_session_store().get_or_create(session_key)
    active_job_ids = snap.jobs_by_id.keys()

    if sess.active_resume is not None and len(sess.active_matches) < len(active_job_ids):
        score_missing_ephemeral_jobs(db, sess)
    session_matches = sess.active_matches

    scores = [
        float(m.match_score)
        for jid, m in session_matches.items()
        if jid in active_job_ids
    ]

    apps = list(sess.applications.values())
    saved_count = sum(1 for a in apps if a.is_saved)
    applied_count = sum(1 for a in apps if (a.status or "").lower() == "applied")
    status_counts = Counter(a.status for a in apps if a.status and a.status != "new")

    missing_counter: Counter = Counter()
    matched_counter: Counter = Counter()
    for jid, m in session_matches.items():
        if jid in active_job_ids:
            for sk in (getattr(m, "matching_skills_json", None) or []):
                matched_counter[sk] += 1
            for msk in (getattr(m, "missing_skills_json", None) or []):
                missing_counter[msk] += 1

    recent_activity = [
        {
            "event": f"Job #{a.job_id} marked {a.status}",
            "detail": "Saved" if a.is_saved else "Application Tracker",
            "timestamp": a.updated_at.isoformat() if a.updated_at else "",
        }
        for a in sorted(apps, key=lambda x: x.updated_at, reverse=True)[:8]
    ]

    tier_90_100 = sum(1 for sc in scores if sc >= 90.0)
    tier_80_89 = sum(1 for sc in scores if 80.0 <= sc < 90.0)
    tier_70_79 = sum(1 for sc in scores if 70.0 <= sc < 80.0)
    tier_below_70 = sum(1 for sc in scores if sc < 70.0)

    buckets = {"0-39%": 0, "40-59%": 0, "60-69%": 0, "70-79%": 0, "80-89%": 0, "90-100%": 0}
    for sc in scores:
        if sc < 40:
            buckets["0-39%"] += 1
        elif sc < 60:
            buckets["40-59%"] += 1
        elif sc < 70:
            buckets["60-69%"] += 1
        elif sc < 80:
            buckets["70-79%"] += 1
        elif sc < 90:
            buckets["80-89%"] += 1
        else:
            buckets["90-100%"] += 1

    last_run = db.query(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).first()

    kpis = dict(snap.global_kpis)
    kpis.update(
        {
            "tier_90_100": tier_90_100,
            "tier_80_89": tier_80_89,
            "tier_70_79": tier_70_79,
            "tier_below_70": tier_below_70,
            "high_match_jobs": tier_90_100 + tier_80_89 + tier_70_79,
            "saved_jobs": saved_count,
            "applied_jobs": applied_count,
            "avg_match_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "max_match_score": round(max(scores), 1) if scores else 0.0,
        }
    )

    charts = dict(snap.global_charts)
    charts.update(
        {
            "score_buckets": buckets,
            "application_statuses": dict(status_counts),
            "top_matching_skills": [{"skill": s, "count": n} for s, n in matched_counter.most_common(8)],
            "top_missing_skills": [{"skill": s, "count": n} for s, n in missing_counter.most_common(8)],
            "pipeline_funnel": [
                {"stage": "Verified Jobs", "count": kpis["total_jobs"]},
                {"stage": "70%+ Matches", "count": tier_90_100 + tier_80_89 + tier_70_79},
                {"stage": "Saved / Tracked", "count": saved_count + sum(1 for a in apps if a.status != "new")},
                {"stage": "Applied", "count": applied_count},
            ],
        }
    )

    return {
        "kpis": kpis,
        "charts": charts,
        "filter_options": snap.filter_options,
        "recent_activity": recent_activity,
        "last_run": {
            "id": last_run.id,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
            "total_fetched": last_run.total_fetched,
            "new_verified_jobs": last_run.new_verified_jobs,
            "matches_computed": last_run.matches_computed,
            "sources_checked_count": len(last_run.sources_checked_json or []),
            "error_message": last_run.error_message,
        }
        if last_run
        else None,
    }
