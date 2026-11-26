"""FastAPI dependencies for database sessions, authentication, and multi-user isolation."""

import re
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.security import constant_time_equals
from backend.db.models import User
from backend.db.session import get_db


def _sanitize_username(raw: Optional[str]) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", (raw or "").strip().lower())
    return clean[:64] or "default"


def require_api_auth(authorization: str | None = Header(default=None)) -> None:
    """Enforce Bearer token auth when API_AUTH_TOKEN is configured."""
    settings = get_settings()
    if not settings.api_auth_token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authorization token.",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not constant_time_equals(token, settings.api_auth_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token.",
        )


def require_scheduler_auth(authorization: str | None = Header(default=None)) -> None:
    """Enforce Bearer token auth for scheduled triggers when SCHEDULER_AUTH_TOKEN is configured."""
    settings = get_settings()
    expected = settings.scheduler_auth_token or settings.api_auth_token
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing scheduler authorization token.",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not constant_time_equals(token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid scheduler authorization token.",
        )


def get_session_id(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> str:
    """Resolve ephemeral session key from header without creating or persisting user accounts."""
    return _sanitize_username(x_session_id or x_user_id or "ephemeral-default")


def get_current_user(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve or provision the active user workspace from X-User-Id header or query param."""
    username = _sanitize_username(x_user_id or user_id or "default")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        display = "Default Workspace" if username == "default" else username.replace("_", " ").title()
        user = User(username=username, display_name=display)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


DBSession = Depends(get_db)
