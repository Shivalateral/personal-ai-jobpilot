"""Shared pytest fixtures for isolated DB, ChromaDB, and FastAPI TestClient."""

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate database, ChromaDB, encryption key, and settings per test."""
    db_file = tmp_path / "test_jobpilot.db"
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("EMBEDDING_OFFLINE_FALLBACK", "true")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("API_AUTH_TOKEN", "")
    monkeypatch.setenv("SCHEDULER_AUTH_TOKEN", "")

    get_settings.cache_clear()

    import backend.db.session as db_session

    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    TestSessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", TestSessionLocal)

    from backend.db import models  # noqa: F401
    from backend.services.corpus_cache import get_corpus_cache
    from backend.services.session_store import get_session_store

    get_corpus_cache().invalidate()
    get_session_store().reset_all()
    db_session.Base.metadata.create_all(bind=engine)

    yield {
        "db_file": db_file,
        "chroma_dir": chroma_dir,
        "engine": engine,
        "SessionLocal": TestSessionLocal,
    }

    get_corpus_cache().invalidate()
    get_session_store().reset_all()
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture()
def db_session(isolated_env) -> Generator[Session, None, None]:
    session = isolated_env["SessionLocal"]()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client(isolated_env) -> Generator[TestClient, None, None]:
    from backend.main import app

    with TestClient(app) as client:
        yield client
