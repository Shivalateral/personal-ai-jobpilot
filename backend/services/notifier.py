"""Notification delivery service (in-app DB records + optional webhook)."""

import logging
from typing import List

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models import JobListing, Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Delivers matching job alerts in-app and optionally via webhook."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_job_notification(
        self,
        db: Session,
        job: JobListing,
        match_score: float,
        user_id: int = 1,
    ) -> Notification:
        """Persist a user-scoped in-app notification for a newly discovered matching job."""
        title = f"New {match_score:.0f}% Match: {job.title} @ {job.company}"
        message = (
            f"Discovered a verified {job.seniority_level.replace('_', ' ')} role in {job.role_category} "
            f"({job.location}). Review the match analysis and official application link in your feed."
        )
        notif = Notification(
            user_id=user_id,
            job_id=job.id,
            title=title[:255],
            message=message,
            match_score=match_score,
            channel="in_app",
            is_read=False,
        )
        db.add(notif)
        db.flush()
        return notif

    def dispatch_external_digest(self, notifications: List[Notification]) -> None:
        """Send optional webhook summary if configured."""
        if not notifications:
            return

        if self.settings.notification_webhook_url:
            self._send_webhook(notifications)

    def _send_webhook(self, notifications: List[Notification]) -> None:
        payload = {
            "app": self.settings.app_name,
            "count": len(notifications),
            "matches": [
                {"title": n.title, "message": n.message, "match_score": n.match_score}
                for n in notifications[:10]
            ],
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(self.settings.notification_webhook_url, json=payload)
        except Exception as exc:
            logger.warning("Webhook notification failed: %s", exc)
