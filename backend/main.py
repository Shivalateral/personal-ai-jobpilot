"""FastAPI application entrypoint for Personal AI JobPilot."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import analytics, chat, health, jobs, notifications, pipeline, profile, resume, session, users
from backend.core.config import get_settings
from backend.core.logging_config import configure_logging
from backend.db.models import DiscoveryRun, JobListing
from backend.db.session import init_db, session_scope
from backend.db.vector_store import get_embedding_service
from backend.scheduler.daily_scheduler import scheduler_manager
from backend.services.corpus_cache import get_corpus_cache

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def _prewarm_embeddings() -> None:
    try:
        mode = get_embedding_service().backend_mode
        logger.info("Pre-warmed embedding service (%s)", mode)
        with session_scope() as db:
            snap = get_corpus_cache().get_snapshot(db, force_check=True)
            job_count = len(snap.jobs)
            logger.info("Pre-warmed SharedJobCorpusCache (%d jobs)", job_count)

        # Fresh cloud deploy bootstrap: if database starts completely empty, trigger discovery once in background
        if (
            job_count == 0
            and settings.app_env not in ("test", "testing")
            and not os.getenv("PYTEST_CURRENT_TEST")
        ):
            logger.info("Fresh deployment detected (0 jobs). Launching initial autonomous discovery bootstrap.")
            from backend.services.pipeline_graph import run_job_pilot_pipeline

            run_job_pilot_pipeline(trigger_type="startup_bootstrap", verify_urls_live=False)
    except Exception as exc:
        logger.warning("Embedding/corpus pre-warm skipped: %s", exc)


def _recover_stale_runs() -> None:
    try:
        with session_scope() as db:
            stale = db.query(DiscoveryRun).filter(DiscoveryRun.status == "running").all()
            for r in stale:
                r.status = "failed"
                r.error_message = "Interrupted by server restart; recovered cleanly."
                r.finished_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.warning("Could not recover stale discovery runs: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize DB, apply safe additive migrations, warm embeddings, and start APScheduler."""
    settings.ensure_directories()
    init_db()
    _recover_stale_runs()
    scheduler_manager.start()
    threading.Thread(target=_prewarm_embeddings, daemon=True).start()
    logger.info("%s backend initialized (env=%s)", settings.app_name, settings.app_env)
    try:
        yield
    finally:
        scheduler_manager.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "Autonomous personal AI job discovery, semantic matching, and career intelligence platform."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(session.router)
app.include_router(users.router)
app.include_router(profile.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(analytics.router)
app.include_router(pipeline.router)
app.include_router(notifications.router)
app.include_router(chat.router)
