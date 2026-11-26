"""Health, readiness, and non-secret AI diagnostics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import get_db
from backend.db.vector_store import get_embedding_service
from backend.services.llm_client import LLMClient

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    settings = get_settings()
    llm_info = LLMClient().status_summary()
    emb_mode = get_embedding_service().backend_mode
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "llm_configured": settings.llm_configured,
        "llm": llm_info,
        "embedding_backend": emb_mode,
        "embedding_model": settings.embedding_model_name,
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}
