"""Pydantic schemas for Conversational AI Assistant."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = "default"
    job_id: Optional[int] = None


class ChatMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    referenced_job_ids: List[int] = Field(default_factory=list)
    created_at: datetime


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    referenced_job_ids: List[int] = Field(default_factory=list)
    used_llm: bool = False
