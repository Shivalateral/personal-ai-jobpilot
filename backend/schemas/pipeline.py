"""Pydantic schemas for Discovery pipeline, Scheduler, and Notifications."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DiscoveryRunRequest(BaseModel):
    trigger_type: str = "manual"
    verify_urls_live: bool = False


class DiscoveryRunResponse(BaseModel):
    id: int
    trigger_type: str
    status: str
    sources_checked: List[str] = Field(default_factory=list)
    total_fetched: int
    new_verified_jobs: int
    duplicates_skipped: int
    rejected_unverified: int
    matches_computed: int
    notifications_created: int
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class NotificationResponse(BaseModel):
    id: int
    job_id: Optional[int] = None
    title: str
    message: str
    match_score: Optional[float] = None
    channel: str
    is_read: bool
    created_at: datetime


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    running: bool
    cron_expression: str
    timezone: str
    next_run_time: Optional[str] = None
