"""APScheduler daily discovery pipeline manager in Asia/Kolkata with restart recovery."""

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.agents.pipeline_graph import DiscoveryPipelineOrchestrator
from backend.core.config import get_settings
from backend.db.models import DiscoveryRun
from backend.db.session import session_scope

logger = logging.getLogger(__name__)


def execute_scheduled_discovery() -> None:
    """Job callback executed daily by APScheduler."""
    logger.info("Starting scheduled daily job discovery run...")
    orchestrator = DiscoveryPipelineOrchestrator()
    with session_scope() as db:
        run = orchestrator.run(db=db, trigger_type="scheduled", verify_urls_live=False)
        logger.info(
            "Scheduled run id=%s finished with status=%s (new_jobs=%s, matches=%s)",
            run.id,
            run.status,
            run.new_verified_jobs,
            run.matches_computed,
        )


def mark_stale_runs_interrupted() -> None:
    """Recover gracefully after restart if a previous run was left in 'running' state."""
    with session_scope() as db:
        stale = db.query(DiscoveryRun).filter(DiscoveryRun.status == "running").all()
        for run in stale:
            run.status = "failed"
            run.error_message = "Interrupted by server restart; recovered cleanly."
            run.finished_at = datetime.now(timezone.utc)


class DailySchedulerManager:
    """Manages lifecycle and inspection of the APScheduler daily discovery job."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._job_id = "daily_jobpilot_discovery"

    def start(self) -> None:
        mark_stale_runs_interrupted()
        if not self.settings.scheduler_enabled:
            logger.info("APScheduler disabled via SCHEDULER_ENABLED=false.")
            return
        if self._scheduler is not None and self._scheduler.running:
            return

        tz = ZoneInfo(self.settings.scheduler_timezone)
        self._scheduler = BackgroundScheduler(timezone=tz)
        trigger = CronTrigger(
            hour=self.settings.scheduler_cron_hour,
            minute=self.settings.scheduler_cron_minute,
            timezone=tz,
        )
        self._scheduler.add_job(
            execute_scheduled_discovery,
            trigger=trigger,
            id=self._job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        self._scheduler.start()
        logger.info(
            "APScheduler started: daily discovery at %02d:%02d %s",
            self.settings.scheduler_cron_hour,
            self.settings.scheduler_cron_minute,
            self.settings.scheduler_timezone,
        )

    def shutdown(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped.")
        self._scheduler = None

    def status(self) -> dict:
        running = bool(self._scheduler and self._scheduler.running)
        next_run = None
        if running and self._scheduler is not None:
            job = self._scheduler.get_job(self._job_id)
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        return {
            "enabled": self.settings.scheduler_enabled,
            "running": running,
            "cron_expression": f"{self.settings.scheduler_cron_minute} {self.settings.scheduler_cron_hour} * * *",
            "timezone": self.settings.scheduler_timezone,
            "next_run_time": next_run,
        }


scheduler_manager = DailySchedulerManager()
