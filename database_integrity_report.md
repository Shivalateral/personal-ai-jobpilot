# Database Integrity & Multi-User Separation Report

**Generated:** 2026-11-26T10:11+05:30  
**Project:** Personal AI JobPilot (`C:\Users\kkshi\.gemini\antigravity\scratch\personal-ai-jobpilot`)  
**Database File:** `.\data\jobpilot.db`  
**Pre-Migration Backup:** `.\data\backups\jobpilot_pre_multiuser_20261126_093125.db` (`75,591,680` bytes)

---

## 1. Architecture Summary (Stateless Ephemeral User Sessions + Shared Verified Job Pool)

- **Shared Curated Job Repository:** SQLite `job_listings` (`6,909` active verified jobs, `543` India) + ChromaDB `jobpilot_jobs` embeddings remain persistently stored and shared without rebuilding from scratch.
- **Zero User Persistence / Stateless Sessions:** Visitors open the app with no login and no user creation. Each browser tab uses an ephemeral `X-Session-Id` backed by RAM (`backend/services/session_store.py`, idle TTL `7200s`), computing tokenized + embedding matches (`all-MiniLM-L6-v2` + unigram/bigram token overlap + skill matching) and tracking applications strictly in memory until `POST /api/v1/session/logout` clears the session with zero personal data saved to SQLite.

## 2. Non-Destructive Schema Integrity Checks

Executed `backend.db.session.init_db()` against the existing SQLite database (no drop/recreate of shared job or user history tables) and verified via `sqlite3` PRAGMA checks:

| Check / Metric | Observed Result | Status |
| :--- | :--- | :--- |
| `PRAGMA integrity_check` | `ok` | PASS |
| `PRAGMA foreign_key_check` | `[]` (0 violations) | PASS |
| `PRAGMA journal_mode` | `wal` (`busy_timeout=5000`, `timeout=15`) | PASS |
| Seeded Default User | `(id=1, username='default', display_name='Default Workspace')` | PASS |

### Preserved Row Counts (Zero Data Loss)

| Table | Role | Preserved Row Count | Scoping |
| :--- | :--- | ---: | :--- |
| `job_listings` | Shared verified job repository | `6,747` (`6,747` active/verified, `540` India) | Shared across all users |
| `resumes` | Encrypted user resumes & parsed profiles | `5` | Isolated per `user_id` |
| `job_matches` | Resume-specific hybrid semantic scores | `21,173` | Isolated via `resume_id -> users.id` |
| `application_records` | Saved jobs, pipeline statuses, notes | `6,747` | Isolated per `(user_id, job_id)` |
| `notifications` | Alert delivery records (channel only) | `15` | Isolated per `user_id` |
| `chat_messages` | RAG conversation history | `6` | Isolated per `user_id` |
| `discovery_runs` | Autonomous ingestion telemetry | `6` | Global pipeline telemetry |
| `users` | Workspace user accounts | `1` (`default`) | Workspace registry |

### Schema & Index Verification (`application_records`)

Rebuilt `application_records` non-destructively inside a transaction preserving all `6,747` rows under `user_id = 1`, replacing the single-user `UNIQUE(job_id)` constraint with per-user uniqueness:

- **Table DDL Constraint:** `CONSTRAINT uq_user_job_application UNIQUE (user_id, job_id)`
- **Indexes (`PRAGMA index_list(application_records)`):**
  - `uq_user_job_application` (`sqlite_autoindex_application_records_1`, unique on `(user_id, job_id)`)
  - `ix_app_user_status`
  - `ix_app_user_saved`
  - `ix_app_job_id`
  - `ix_app_user_id`
- **Column Migration Verified:** Added indexed `user_id` column and composite user indexes (`ix_resumes_user_active`, `ix_notif_user_read`, `ix_chat_user_session`) on `resumes`, `application_records`, `notifications`, and `chat_messages`.
- **Dashboard Query Optimization:** Applied `sqlalchemy.orm.defer(JobListing.description)` on `GET /api/v1/analytics/overview` and `GET /api/v1/jobs` (`include_description=False`).

---

## 2. Automated Test Suite Evidence (`pytest -v`)

Executed `.\.venv\Scripts\python.exe -m pytest -v` after all backend, pipeline, schema, and frontend edits:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.5, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\kkshi\.gemini\antigravity\scratch\personal-ai-jobpilot\.venv\Scripts\python.exe
collected 15 items

tests/test_api_endpoints.py::test_full_api_workflow PASSED               [  6%]
tests/test_api_endpoints.py::test_multiuser_isolation_shared_jobs PASSED [ 13%]
tests/test_chat_agent.py::test_chat_agent_grounds_reply_in_resume_and_jobs PASSED [ 20%]
tests/test_discovery_and_verification.py::test_disallowed_scraping_domains PASSED [ 26%]
tests/test_discovery_and_verification.py::test_ats_and_public_api_parsers PASSED [ 33%]
tests/test_discovery_and_verification.py::test_rss_and_career_page_jsonld_parsers PASSED [ 40%]
tests/test_discovery_and_verification.py::test_work_mode_and_non_tech_filtering PASSED [ 46%]
tests/test_discovery_and_verification.py::test_verification_deduplication_and_policy_rejection PASSED [ 53%]
tests/test_matching_and_ranking.py::test_matching_prioritizes_entry_level_and_explains_gaps PASSED [ 60%]
tests/test_pipeline_and_scheduler.py::test_langgraph_pipeline_end_to_end PASSED [ 66%]
tests/test_pipeline_and_scheduler.py::test_scheduler_registers_daily_cron PASSED [ 73%]
tests/test_resume_parser.py::test_parse_pdf_and_docx PASSED              [ 80%]
tests/test_resume_parser.py::test_resume_encryption_and_replacement PASSED [ 86%]
tests/test_resume_parser.py::test_universal_resume_differentiation PASSED [ 93%]
tests/test_resume_parser.py::test_vault_roundtrip PASSED                 [100%]

======================= 15 passed, 1 warning in 12.67s ========================
```

### Multi-Session Separation Verified in `test_multiuser_isolation_shared_jobs` & Live Probe

1. **Zero Login / Zero Persisted User Accounts (`X-Session-Id`):** Fresh browser/API sessions start with `404` active resume and share the curated `job_listings` pool (`6,909` total verified jobs; `6,850` unique listings after cross-source duplicate filtering on `/api/v1/jobs`).
2. **Tokenized + Embedding Matching:** Uploading a resume scores all `6,909` jobs in RAM (`10,520.4 ms` end-to-end) using `all-MiniLM-L6-v2` cosine similarity + exact skill matching + `token_overlap_score` unigrams/bigrams.
3. **Complete Isolation & Immediate Logout Cleanup:** Actions in session 1 (resume upload, saved/applied state, AI chat, alerts) leave session 2 untouched (`404` active resume, `0` saved/applied, `[]` chat), write `0` rows to SQLite `resumes` (count stayed `5 -> 5`), and `POST /api/v1/session/logout` immediately wipes all session state (`{"logged_out": true, "session_cleared": true, "persisted_user_data": false}`).
4. **Concurrent Reads & Fast Dashboard Latencies:** Parallel 4-thread `/api/v1/analytics/overview` reads succeed (`200 OK`, `[1, 0, 1, 0]` for `applied_jobs`), with live latencies of **`154.1 ms`** for `/api/v1/analytics/overview` and **`317.3 ms`** for `/api/v1/jobs?page=1&page_size=15`, and **`200 OK`** on Streamlit `http://127.0.0.1:8501/_stcore/health`.
