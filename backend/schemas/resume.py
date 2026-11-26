"""Pydantic schemas for universal Resume upload, activation, review/edit, and profile responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ResumeProfileResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    candidate_name: Optional[str] = None
    graduation_year: Optional[int] = None
    summary: str = ""
    skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    languages_frameworks: List[str] = Field(default_factory=list)
    domain_knowledge: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    experience_level: str = "entry_level"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ResumeProfileUpdateRequest(BaseModel):
    candidate_name: Optional[str] = None
    graduation_year: Optional[int] = Field(default=None, ge=2000, le=2035)
    summary: Optional[str] = None
    experience_level: Optional[str] = None
    skills: Optional[List[str]] = None
    soft_skills: Optional[List[str]] = None
    domain_knowledge: Optional[List[str]] = None
    target_roles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    qualifications: Optional[List[str]] = None


class ResumeUploadResponse(BaseModel):
    message: str
    replaced_previous: bool = False
    profile: ResumeProfileResponse
    jobs_rescored: int = 0
