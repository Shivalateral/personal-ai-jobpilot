"""Ephemeral session lifecycle endpoints (stateless session inspect and logout/clear)."""

from fastapi import APIRouter, Depends, status

from backend.api.deps import get_session_id, require_api_auth
from backend.services.session_store import get_session_store

router = APIRouter(
    prefix="/api/v1/session",
    tags=["Session"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("/status")
def get_session_status(session_key: str = Depends(get_session_id)):
    """Return non-persistent status for the current ephemeral browser session."""
    sess = get_session_store().get_or_create(session_key)
    apps = list(sess.applications.values())
    return {
        "session_id": session_key,
        "has_resume": sess.active_resume is not None,
        "saved_jobs": sum(1 for a in apps if a.is_saved),
        "applied_jobs": sum(1 for a in apps if (a.status or "").lower() == "applied"),
        "persisted_user_data": False,
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
@router.delete("", status_code=status.HTTP_200_OK)
def logout_and_clear_session(session_key: str = Depends(get_session_id)):
    """Immediately discard all temporary resume, match, tracker, and chat data for this session."""
    existed = get_session_store().clear_session(session_key)
    return {
        "logged_out": True,
        "session_cleared": existed,
        "persisted_user_data": False,
    }
