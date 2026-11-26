"""User Career Profile, Theme, Automatic Settings, Email Verification & Account endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_api_auth
from backend.db.models import User, UserPreference
from backend.db.session import get_db

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["Career Profile & Settings"],
    dependencies=[Depends(require_api_auth)],
)


class ProfilePreferencesPayload(BaseModel):
    theme: Optional[str] = None
    preferred_roles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    countries: Optional[List[str]] = None
    work_modes: Optional[List[str]] = None
    min_experience: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    max_experience: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    employment_types: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    salary_preference: Optional[str] = None
    education_qualifications: Optional[str] = None
    email_address: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    auto_daily_discovery: Optional[bool] = None
    fresher_filter_default: Optional[bool] = None
    dedup_enabled: Optional[bool] = None
    persist_resume_consent: Optional[bool] = None
    saved_searches: Optional[List[Dict[str, Any]]] = None


class EmailVerifyRequest(BaseModel):
    email_address: str = Field(..., min_length=5, max_length=255)


def _get_or_create_prefs(db: Session, user: User) -> UserPreference:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if prefs is None:
        prefs = UserPreference(
            user_id=user.id,
            theme="dark",
            preferred_locations_json=["India", "Remote"],
            countries_json=["India"],
            work_modes_json=["remote", "hybrid", "onsite"],
            employment_types_json=["Full-time", "Internship"],
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def _serialize_prefs(prefs: UserPreference, user: User) -> Dict[str, Any]:
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "theme": prefs.theme,
        "preferred_roles": prefs.preferred_roles_json or [],
        "preferred_locations": prefs.preferred_locations_json or [],
        "countries": prefs.countries_json or [],
        "work_modes": prefs.work_modes_json or [],
        "min_experience": prefs.min_experience,
        "max_experience": prefs.max_experience,
        "employment_types": prefs.employment_types_json or [],
        "skills": prefs.skills_json or [],
        "salary_preference": prefs.salary_preference or "",
        "education_qualifications": prefs.education_qualifications or "",
        "email_address": prefs.email_address or "",
        "email_verified": bool(prefs.email_verified),
        "notifications_enabled": bool(prefs.notifications_enabled),
        "auto_daily_discovery": bool(prefs.auto_daily_discovery),
        "fresher_filter_default": bool(prefs.fresher_filter_default),
        "dedup_enabled": bool(prefs.dedup_enabled),
        "persist_resume_consent": bool(prefs.persist_resume_consent),
        "saved_searches": prefs.saved_searches_json or [],
        "updated_at": prefs.updated_at.isoformat() if prefs.updated_at else None,
    }


@router.get("/preferences")
def get_profile_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = _get_or_create_prefs(db, current_user)
    return _serialize_prefs(prefs, current_user)


@router.put("/preferences")
def update_profile_preferences(
    payload: ProfilePreferencesPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = _get_or_create_prefs(db, current_user)
    data = payload.model_dump(exclude_unset=True)

    json_map = {
        "preferred_roles": "preferred_roles_json",
        "preferred_locations": "preferred_locations_json",
        "countries": "countries_json",
        "work_modes": "work_modes_json",
        "employment_types": "employment_types_json",
        "skills": "skills_json",
        "saved_searches": "saved_searches_json",
    }
    for req_k, attr in json_map.items():
        if req_k in data and data[req_k] is not None:
            setattr(prefs, attr, data[req_k])

    for scalar in (
        "theme",
        "min_experience",
        "max_experience",
        "salary_preference",
        "education_qualifications",
        "notifications_enabled",
        "auto_daily_discovery",
        "fresher_filter_default",
        "dedup_enabled",
        "persist_resume_consent",
    ):
        if scalar in data and data[scalar] is not None:
            setattr(prefs, scalar, data[scalar])

    if "email_address" in data and data["email_address"] is not None:
        new_email = data["email_address"].strip()
        if new_email != (prefs.email_address or ""):
            prefs.email_address = new_email
            prefs.email_verified = False

    db.commit()
    db.refresh(prefs)
    return _serialize_prefs(prefs, current_user)


@router.post("/email/verify")
def verify_notification_email(
    payload: EmailVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    email = payload.email_address.strip()
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid email address.")
    prefs = _get_or_create_prefs(db, current_user)
    prefs.email_address = email
    prefs.email_verified = True
    db.commit()
    db.refresh(prefs)
    return {"email_address": prefs.email_address, "email_verified": True}
