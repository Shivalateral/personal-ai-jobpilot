"""Notification Agent: alerts the user about newly discovered high-matching jobs."""

import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models import JobListing, JobMatch, Notification
from backend.services.notifier import NotificationService

logger = logging.getLogger(__name__)


class NotificationAgent:
    """Evaluates newly matched jobs against threshold and emits notifications."""

    def __init__(self, notifier: Optional[NotificationService] = None) -> None:
        self.settings = get_settings()
        self.notifier = notifier or NotificationService()

    def notify_matches(
        self,
        db: Session,
        matched_pairs: List[Tuple[JobListing, JobMatch]],
        min_score: Optional[float] = None,
    ) -> List[Notification]:
        """Create in-app notifications and send external digest for qualifying new matches."""
        threshold = (
            self.settings.discovery_min_match_notify if min_score is None else min_score
        )
        created: List[Notification] = []

        for job, match in matched_pairs:
            if match.match_score >= threshold:
                user_id = getattr(match.resume, "user_id", 1) if getattr(match, "resume", None) else 1
                notif = self.notifier.create_job_notification(
                    db=db,
                    job=job,
                    match_score=match.match_score,
                    user_id=user_id,
                )
                created.append(notif)

        db.commit()
        if created:
            self.notifier.dispatch_external_digest(created)
            logger.info("NotificationAgent created %d notification(s).", len(created))
        return created
