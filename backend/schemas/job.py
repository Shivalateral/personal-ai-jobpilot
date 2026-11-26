"""Pydantic schemas for Job listings, India Geography, Match Tiers, and Application tracking."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ApplicationStatus = Literal[
    "new",
    "Saved",
    "Interested",
    "Pending Confirmation",
    "Applied",
    "Assessment",
    "Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
    "Selected",
    "saved",
    "interested",
    "pending confirmation",
    "reviewing",
    "applied",
    "assessment",
    "interview",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
    "dismissed",
]


class JobMatchSummary(BaseModel):
    match_score: float
    semantic_score: float
    skill_score: float
    entry_level_bonus: float
    eligibility_status: str = "Eligible"
    matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    recommended_improvements: List[str] = Field(default_factory=list)
    explanation: str = ""
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)


class ApplicationStateResponse(BaseModel):
    status: str = "new"
    is_saved: bool = False
    user_approved: bool = False
    dismissed: bool = False
    notes: str = ""
    saved_at: Optional[datetime] = None
    clicked_apply_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    follow_up_date: Optional[datetime] = None
    status_history: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class JobListingResponse(BaseModel):
    id: int
    source: str
    company: str
    company_logo_url: Optional[str] = None
    title: str
    location: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    city_tier: Optional[str] = None
    work_mode: str = "unknown"
    is_remote: bool
    role_category: str
    domain_tags: List[str] = Field(default_factory=list)
    seniority_level: str
    is_entry_level_priority: bool
    fresher_eligible: bool = False
    experience_requirement: Optional[str] = None
    salary_or_stipend: Optional[str] = None
    employment_type: Optional[str] = None
    description: str = ""
    required_skills: List[str] = Field(default_factory=list)
    apply_url: str
    source_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    discovered_at: datetime
    last_verified_at: Optional[datetime] = None
    verified: bool
    is_expired: bool = False
    match: Optional[JobMatchSummary] = None
    application: ApplicationStateResponse = Field(default_factory=ApplicationStateResponse)


class ApplicationUpdateRequest(BaseModel):
    status: Optional[ApplicationStatus] = None
    is_saved: Optional[bool] = None
    user_approved: Optional[bool] = None
    dismissed: Optional[bool] = None
    clicked_apply: Optional[bool] = None
    notes: Optional[str] = None
    follow_up_date: Optional[datetime] = None


class JobListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 25
    total_pages: int = 1
    items: List[JobListingResponse]
    closest_matches: List[JobListingResponse] = Field(default_factory=list)
