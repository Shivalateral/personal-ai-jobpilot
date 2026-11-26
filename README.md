# Personal AI JobPilot — Autonomous Job Discovery Platform

Personal AI JobPilot is a production-oriented, privacy-first personal job discovery and matching platform. Upload your resume once (PDF or DOCX), and the platform autonomously discovers new **Data Analyst, Data Scientist, AI/ML, and Internship** opportunities every day (prioritizing fresh graduate and entry-level roles), computes explainable semantic + skill-gap match scores, and presents verified official company application links.

> **Core Safety & Ethics Guarantees**
> - Never uses unauthorized LinkedIn, Indeed, or Glassdoor scraping.
> - Enforces `robots.txt` policies and polite per-domain rate limits.
> - Never fabricates job vacancies, match scores, or application URLs.
> - Never automatically submits job applications — manual user review and explicit approval (`user_approved=true`) are enforced before marking any job as applied.
> - Encrypts raw resume text at rest with Fernet symmetric encryption and redacts PII/keys from logs.

---

## Architecture

The backend orchestrates 6 modular agents using **LangGraph**:

1. **Resume Intelligence Agent** (`backend/agents/resume_agent.py`): Parses PDF (`PyMuPDF`) and DOCX (`python-docx`), extracts skills, education, experience, projects, qualifications, and target roles, encrypts raw text via `ResumeVault`, supports clean resume replacement, indexes embeddings in ChromaDB, and re-scores existing verified jobs.
2. **Job Discovery Agent** (`backend/agents/discovery_agent.py`): Connects to official public ATS APIs (**Greenhouse**, **Lever**, **Ashby**), authorized public job APIs (**Remotive**, **Arbeitnow**), public **RSS/Atom** feeds, and `robots.txt`-compliant **JSON-LD company career pages**.
3. **Job Verification Agent** (`backend/agents/verification_agent.py`): Enforces domain allow/block policies, optionally verifies live HTTP reachability, deduplicates via canonical SHA-256 keys, stores verified listings in PostgreSQL/SQLite, and indexes them in ChromaDB.
4. **Job Matching Agent** (`backend/agents/matching_agent.py`): Combines SentenceTransformer embeddings (`all-MiniLM-L6-v2` with offline deterministic fallback), canonical skill overlap, entry-level/fresh-grad priority weighting, and configurable LLM rationale (Qwen / Llama / GPT via OpenAI-compatible API).
5. **Notification Agent** (`backend/agents/notification_agent.py`): Emits in-app alerts and optional webhook notifications for high-matching new jobs.
6. **Conversational AI Agent** (`backend/agents/chat_agent.py`): LangGraph RAG assistant answering questions about discovered jobs, required skills, and resume improvements using stored resume and job context.

---

## Local Setup

### 1. Environment Configuration
```bash
cp .env.example .env
```
Edit `.env` to configure:
- `DATABASE_URL`: PostgreSQL URL (`postgresql+psycopg2://...`) or SQLite (`sqlite:///./data/jobpilot.db`) for zero-setup local use.
- `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`: Works with OpenAI (`gpt-4o-mini`), Ollama (`http://localhost:11434/v1`, `qwen2.5:7b` or `llama3.1`), Groq, or vLLM. If `LLM_API_KEY` is omitted, deterministic extraction/explanation fallbacks keep the full platform operational.
- `RESUME_ENCRYPTION_KEY`: Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

### 2. Install & Run Locally
```bash
python -m venv .venv
# Activate .venv, then:
pip install -r requirements.txt

# Start Backend (terminal 1)
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Start Frontend (terminal 2)
streamlit run frontend/app.py --server.port 8501
```
On Windows PowerShell you can also run `.\run_local.ps1`.

### 3. Run with Docker Compose (PostgreSQL + Backend + Frontend)
```bash
docker compose up --build
```
- Backend API & Swagger docs: `http://localhost:8000/docs`
- Streamlit Dashboard: `http://localhost:8501`

---

## Automated Tests
```bash
pytest -v
```

---

## Publishing & Cloud Deployment

### Option A: GitHub + Render (1-Click Blueprint)
1. Push this repository to GitHub (`.gitignore` already excludes `.env`, `data/`, `*.db`, and `.venv/`):
   ```bash
   git init
   git add .
   git commit -m "Release Personal AI JobPilot"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/personal-ai-jobpilot.git
   git push -u origin main
   ```
2. On [Render](https://dashboard.render.com), choose **New → Blueprint**, connect your GitHub repository, and apply [`render.yaml`](render.yaml).
3. Enter your `LLM_API_KEY` (Gemini) / `LLM_FALLBACK_API_KEY` (OpenAI) secrets in the Render Environment tab. First startup automatically bootstraps verified MNC & Startup jobs into PostgreSQL.

### Option B: Railway or Streamlit Community Cloud + Cloud Backend
- **Backend**: Deploy `Dockerfile.backend` on Railway / Render / Cloud Run with PostgreSQL `DATABASE_URL` and `RESUME_ENCRYPTION_KEY`.
- **Frontend**: Deploy `frontend/app.py` on **Streamlit Community Cloud** (pointing to your GitHub repo) and add `FRONTEND_API_URL = "https://<your-backend-url>"` under Streamlit Secrets / Environment Variables.

### Option C: Google Cloud Run
See [deploy/cloudrun.md](deploy/cloudrun.md) and [cloudbuild.yaml](cloudbuild.yaml) for full Google Cloud Run, Cloud SQL (PostgreSQL), Secret Manager, and Cloud Scheduler instructions.
