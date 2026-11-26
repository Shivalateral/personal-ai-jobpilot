"""User workspace endpoints supporting concurrent isolated users on a shared job repository."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import _sanitize_username, require_api_auth
from backend.db.models import User
from backend.db.session import get_db

router = APIRouter(prefix="/api/v1/users", tags=["Users"], dependencies=[Depends(require_api_auth)])


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str


@router.get("", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserResponse(id=u.id, username=u.username, display_name=u.display_name) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_or_get_user(payload: UserCreateRequest, db: Session = Depends(get_db)):
    username = _sanitize_username(payload.username)
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid username.")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return UserResponse(id=existing.id, username=existing.username, display_name=existing.display_name)
    display = payload.display_name.strip() or username.replace("_", " ").title()
    user = User(username=username, display_name=display)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username, display_name=user.display_name)
