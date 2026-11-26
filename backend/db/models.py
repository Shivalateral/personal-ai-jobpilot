"""SQLAlchemy ORM models for multi-user Personal AI JobPilot with shared job repository."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account/workspace isolating resumes, matches, saved jobs, applications, and chat."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    resumes: Mapped[List["Resume"]] = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[List["ApplicationRecord"]] = relationship(
        "ApplicationRecord", back_populates="user", cascade="all, delete-orphan"
    )


class Resume(Base):
    """User-scoped parsed resume intelligence and encrypted raw resume text."""

    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_user_active", "user_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    encrypted_raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)

    skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    soft_skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    languages_frameworks_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    domain_knowledge_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    achievements_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    education_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    experience_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    projects_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    qualifications_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    target_roles_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_locations_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    keywords_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    experience_level: Mapped[str] = mapped_column(String(64), default="entry_level", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="resumes")
    matches: Mapped[List["JobMatch"]] = relationship(
        "JobMatch", back_populates="resume", cascade="all, delete-orphan"
    )


class JobListing(Base):
    """Shared verified, deduplicated job repository accessible to all users."""

    __tablename__ = "job_listings"
    __table_args__ = (
        Index(
            "ix_job_feed_filter",
            "is_active",
            "is_expired",
            "verified",
            "work_mode",
            "is_entry_level_priority",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_logo_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(255), default="Unspecified", nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    city_tier: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    work_mode: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False, index=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    role_category: Mapped[str] = mapped_column(String(64), default="General & Other", nullable=False, index=True)
    domain_tags_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    seniority_level: Mapped[str] = mapped_column(String(64), default="entry_level", nullable=False, index=True)
    is_entry_level_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    fresher_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    experience_requirement: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    salary_or_stipend: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    apply_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    matches: Mapped[List["JobMatch"]] = relationship(
        "JobMatch", back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[List["ApplicationRecord"]] = relationship(
        "ApplicationRecord", back_populates="job", cascade="all, delete-orphan"
    )


class JobMatch(Base):
    """Resume-scoped explainable match score against the shared JobListing repository."""

    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_resume_job_match"),
        Index("ix_match_resume_score", "resume_id", "match_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True)

    match_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_score: Mapped[float] = mapped_column(Float, nullable=False)
    entry_level_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(32), default="Eligible", nullable=False)

    matching_skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    missing_skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    recommended_improvements_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    score_breakdown_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    resume: Mapped["Resume"] = relationship("Resume", back_populates="matches")
    job: Mapped["JobListing"] = relationship("JobListing", back_populates="matches")


class ApplicationRecord(Base):
    """User-isolated bookmarking and manual application tracking against shared jobs."""

    __tablename__ = "application_records"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_application"),
        Index("ix_app_user_saved", "user_id", "is_saved"),
        Index("ix_app_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_apply_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    follow_up_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status_history_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped["JobListing"] = relationship("JobListing", back_populates="applications")


class DiscoveryRun(Base):
    """Audit log for shared job discovery pipeline runs."""

    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    sources_checked_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    total_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_verified_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_unverified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_computed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notifications_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    """User-scoped notifications emitted when high-matching jobs are discovered."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_user_read", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False, index=True)
    job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="in_app", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ChatMessage(Base):
    """User-scoped conversation history for the Interactive AI Assistant."""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_user_session", "user_id", "session_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_job_ids_json: Mapped[List[int]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserPreference(Base):
    """User-isolated career profile, UI theme, automatic discovery, and notification preferences."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, default=1, nullable=False, index=True)
    theme: Mapped[str] = mapped_column(String(16), default="dark", nullable=False)
    preferred_roles_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_locations_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    countries_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    work_modes_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    min_experience: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_experience: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    employment_types_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    skills_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    salary_preference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    education_qualifications: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_daily_discovery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fresher_filter_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dedup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    persist_resume_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saved_searches_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
