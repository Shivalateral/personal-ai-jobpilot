"""Ephemeral session-scoped notifications (cleared when user logs out)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_session_id, require_api_auth
from backend.schemas.pipeline import NotificationResponse
from backend.services.session_store import get_session_store

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("", response_model=List[NotificationResponse])
def list_notifications(
    unread_only: bool = False,
    session_key: str = Depends(get_session_id),
):
    sess = get_session_store().get_or_create(session_key)
    rows = list(reversed(sess.notifications))
    if unread_only:
        rows = [n for n in rows if not n.is_read]
    return [
        NotificationResponse(
            id=n.id,
            job_id=n.job_id,
            title=n.title,
            message=n.message,
            match_score=n.match_score,
            channel=n.channel,
            is_read=n.is_read,
            created_at=n.created_at,
        )
        for n in rows[:50]
    ]


@router.post("/{notification_id}/read", status_code=status.HTTP_200_OK)
def mark_notification_read(
    notification_id: int,
    session_key: str = Depends(get_session_id),
):
    sess = get_session_store().get_or_create(session_key)
    notif = next((n for n in sess.notifications if n.id == notification_id), None)
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notif.is_read = True
    return {"id": notification_id, "is_read": True}
