"""SQLAlchemy engine, safe non-destructive multi-user migrations, and session management."""

import logging
from contextlib import contextmanager
from typing import Dict, Generator, Set

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {}
    engine_kwargs = {"pool_pre_ping": True}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 15
    else:
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20

    eng = create_engine(url, connect_args=connect_args, **engine_kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA temp_store=MEMORY;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return eng


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def _migrate_application_records_multiuser(conn) -> None:
    """Upgrade application_records from single-user UNIQUE(job_id) to UNIQUE(user_id, job_id) without data loss."""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(application_records)")).fetchall()}
    if "user_id" in cols:
        return

    conn.execute(text("PRAGMA foreign_keys=OFF;"))
    conn.execute(
        text(
            """
            CREATE TABLE application_records_new (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER DEFAULT 1 NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id INTEGER NOT NULL REFERENCES job_listings(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL,
                is_saved BOOLEAN NOT NULL,
                user_approved BOOLEAN NOT NULL,
                notes TEXT NOT NULL,
                applied_at DATETIME,
                follow_up_date DATETIME,
                status_history_json JSON DEFAULT '[]' NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_user_job_application UNIQUE (user_id, job_id)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO application_records_new (
                id, user_id, job_id, status, is_saved, user_approved, notes,
                applied_at, follow_up_date, status_history_json, updated_at
            )
            SELECT
                id, 1, job_id, status, is_saved, user_approved, notes,
                applied_at, follow_up_date, COALESCE(status_history_json, '[]'), updated_at
            FROM application_records
            """
        )
    )
    conn.execute(text("DROP TABLE application_records"))
    conn.execute(text("ALTER TABLE application_records_new RENAME TO application_records"))
    conn.execute(text("PRAGMA foreign_keys=ON;"))
    logger.info("Migrated 'application_records' to multi-user UNIQUE(user_id, job_id) preserving all rows.")


def _apply_additive_migrations() -> None:
    """Safely add new columns, multi-user user_id mappings, and indexes without losing records."""
    migrations: Dict[str, Dict[str, str]] = {
        "resumes": {
            "user_id": "INTEGER DEFAULT 1 NOT NULL",
            "graduation_year": "INTEGER",
            "soft_skills_json": "JSON DEFAULT '[]' NOT NULL",
            "languages_frameworks_json": "JSON DEFAULT '[]' NOT NULL",
            "domain_knowledge_json": "JSON DEFAULT '[]' NOT NULL",
            "achievements_json": "JSON DEFAULT '[]' NOT NULL",
            "preferred_locations_json": "JSON DEFAULT '[]' NOT NULL",
            "keywords_json": "JSON DEFAULT '[]' NOT NULL",
        },
        "job_listings": {
            "city": "VARCHAR(128)",
            "state": "VARCHAR(128)",
            "country": "VARCHAR(128)",
            "city_tier": "VARCHAR(32)",
            "work_mode": "VARCHAR(32) DEFAULT 'unknown' NOT NULL",
            "domain_tags_json": "JSON DEFAULT '[]' NOT NULL",
            "fresher_eligible": "BOOLEAN DEFAULT 0 NOT NULL",
            "experience_requirement": "VARCHAR(128)",
            "salary_or_stipend": "VARCHAR(128)",
            "last_verified_at": "DATETIME",
            "is_expired": "BOOLEAN DEFAULT 0 NOT NULL",
        },
        "job_matches": {
            "eligibility_status": "VARCHAR(32) DEFAULT 'Eligible' NOT NULL",
            "recommended_improvements_json": "JSON DEFAULT '[]' NOT NULL",
        },
        "notifications": {
            "user_id": "INTEGER DEFAULT 1 NOT NULL",
        },
        "chat_messages": {
            "user_id": "INTEGER DEFAULT 1 NOT NULL",
        },
        "application_records": {
            "saved_at": "DATETIME",
            "clicked_apply_at": "DATETIME",
            "dismissed": "BOOLEAN DEFAULT 0 NOT NULL",
        },
    }

    with engine.begin() as conn:
        if engine.dialect.name != "sqlite":
            return

        # Seed default user id=1 so existing records map cleanly
        existing_default = conn.execute(text("SELECT id FROM users WHERE id = 1")).fetchone()
        if not existing_default:
            conn.execute(
                text(
                    "INSERT INTO users (id, username, display_name, created_at) "
                    "VALUES (1, 'default', 'Default Workspace', CURRENT_TIMESTAMP)"
                )
            )

        for table_name, columns in migrations.items():
            existing: Set[str] = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            }
            for col_name, col_def in columns.items():
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    logger.info("Migrated table '%s': added column '%s'", table_name, col_name)

        _migrate_application_records_multiuser(conn)

        index_statements = [
            "CREATE INDEX IF NOT EXISTS ix_resumes_user_id ON resumes (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_resumes_user_active ON resumes (user_id, is_active)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_work_mode ON job_listings (work_mode)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_city ON job_listings (city)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_state ON job_listings (state)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_country ON job_listings (country)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_city_tier ON job_listings (city_tier)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_fresher_eligible ON job_listings (fresher_eligible)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_is_expired ON job_listings (is_expired)",
            "CREATE INDEX IF NOT EXISTS ix_job_listings_posted_at ON job_listings (posted_at)",
            "CREATE INDEX IF NOT EXISTS ix_job_feed_filter ON job_listings (is_active, is_expired, verified, work_mode, is_entry_level_priority)",
            "CREATE INDEX IF NOT EXISTS ix_match_resume_score ON job_matches (resume_id, match_score)",
            "CREATE INDEX IF NOT EXISTS ix_app_user_id ON application_records (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_app_job_id ON application_records (job_id)",
            "CREATE INDEX IF NOT EXISTS ix_app_user_saved ON application_records (user_id, is_saved)",
            "CREATE INDEX IF NOT EXISTS ix_app_user_status ON application_records (user_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_notif_user_read ON notifications (user_id, is_read)",
            "CREATE INDEX IF NOT EXISTS ix_chat_user_session ON chat_messages (user_id, session_id)",
        ]
        for stmt in index_statements:
            conn.execute(text(stmt))


def init_db() -> None:
    """Create database tables and apply non-destructive additive migrations."""
    from backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
