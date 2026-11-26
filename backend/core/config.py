"""Application configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """Centralized, environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Personal AI JobPilot"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_api_url: str = "http://127.0.0.1:8000"

    # Security & Privacy
    resume_encryption_key: str = ""
    api_auth_token: str = ""
    scheduler_auth_token: str = ""

    # Database (PostgreSQL primary; SQLite fallback for local dev)
    database_url: str = f"sqlite:///{(DATA_DIR / 'jobpilot.db').as_posix()}"

    # Vector Database & Embeddings
    chroma_persist_dir: str = str(DATA_DIR / "chroma")
    chroma_collection_jobs: str = "jobpilot_jobs"
    chroma_collection_resumes: str = "jobpilot_resumes"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_offline_fallback: bool = False

    # LLM (OpenAI-compatible: Gemini, OpenAI GPT, Ollama Qwen/Llama, Groq, vLLM)
    llm_provider: str = "gemini_openai_compatible"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-3.8-flash"
    llm_api_key: str = ""
    llm_fallback_base_url: str = ""
    llm_fallback_model: str = ""
    llm_fallback_api_key: str = ""
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 30

    # Autonomous Job Discovery
    discovery_user_agent: str = (
        "PersonalAIJobPilot/1.0 (+https://github.com/personal-ai-jobpilot; respectful-ats-client)"
    )
    discovery_request_timeout: int = 12
    discovery_rate_limit_seconds: float = 0.35
    discovery_min_match_notify: float = 70.0
    preferred_locations: str = "Hyderabad,Bangalore,Bengaluru,Chennai,India,Remote"

    greenhouse_boards: str = (
        "databricks,scaleai,anthropic,druva,mongodb,stripe,gitlab,elastic,airbnb,coinbase,"
        "datadog,groww,twilio,figma,cloudflare,discord,canonical,reddit,roblox,pinterest,"
        "coursera,duolingo,spacex,zscaler,rubrik,fivetran,okta,waymo,toast,samsara,"
        "brex,adyen,affirm,lyft,grafanalabs,epicgames,klaviyo,nuro,instacart,vercel,"
        "chime,inmobi,geotab,monzo,dropbox,mixpanel,launchdarkly,n26,slice,wise,"
        "hootsuite,cockroachlabs,airtable,netlify,purestorage,celonis,deliveroo,contentful,pine"
    )
    lever_companies: str = "paytm,meesho,cred,spotify,binance,palantir"
    ashby_companies: str = (
        "sarvam,perplexity,ramp,linear,cohere,openai,elevenlabs,langchain,modal,replit,"
        "notion,vercel,supabase,1password,wealthsimple,float,koho,vanta,drata,benevity,"
        "oyster,lightspeed,harvey,cognition,baseten,mercor,fireworks,cursor,suno,writer,"
        "livekit,anyscale,pika,midjourney,resend,posthog,vapi,poolside,runway,neon,deliveroo"
    )
    smartrecruiters_companies: str = "BoschGroup,NielsenIQ,AbbVie,Visa,SAP,ServiceNow,Wipro,PublicisGroupe,Siemens,Continental,Sodexo,Uber"
    workday_endpoints: str = ""
    enable_remotive_api: bool = True
    enable_arbeitnow_api: bool = True
    enable_jobicy_api: bool = True
    enable_himalayas_api: bool = True
    enable_remoteok_api: bool = True
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"
    rss_feed_urls: str = (
        "https://weworkremotely.com/remote-jobs.rss,"
        "https://weworkremotely.com/categories/remote-programming-jobs.rss,"
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss,"
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss,"
        "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss"
    )
    career_page_urls: str = ""

    # Daily Scheduler
    scheduler_enabled: bool = True
    scheduler_cron_hour: int = Field(default=8, ge=0, le=23)
    scheduler_cron_minute: int = Field(default=30, ge=0, le=59)
    scheduler_timezone: str = "Asia/Kolkata"

    # Notifications (in-app + optional webhook)
    notification_webhook_url: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_postgres_scheme(cls, value: str) -> str:
        # Cloud Run / Heroku sometimes provide postgres:// instead of postgresql+psycopg2://
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg2://", 1)
        return value

    @model_validator(mode="after")
    def _render_memory_guard(self):
        # On constrained free cloud tiers (Render / Streamlit Cloud), default to lightweight hash embeddings unless overridden
        is_streamlit_cloud = str(BASE_DIR).startswith("/mount/src") or bool(os.getenv("STREAMLIT_SHARING_MODE"))
        if (os.getenv("RENDER") or is_streamlit_cloud) and "EMBEDDING_OFFLINE_FALLBACK" not in os.environ:
            self.embedding_offline_fallback = True
        return self

    def parse_csv_list(self, raw: str) -> List[str]:
        """Split a comma-separated config string into clean non-empty tokens."""
        return [item.strip() for item in (raw or "").split(",") if item.strip()]

    @property
    def greenhouse_board_list(self) -> List[str]:
        return self.parse_csv_list(self.greenhouse_boards)

    @property
    def lever_company_list(self) -> List[str]:
        return self.parse_csv_list(self.lever_companies)

    @property
    def ashby_company_list(self) -> List[str]:
        return self.parse_csv_list(self.ashby_companies)

    @property
    def smartrecruiters_company_list(self) -> List[str]:
        return self.parse_csv_list(self.smartrecruiters_companies)

    @property
    def workday_endpoint_list(self) -> List[str]:
        return self.parse_csv_list(self.workday_endpoints)

    @property
    def rss_feed_list(self) -> List[str]:
        return self.parse_csv_list(self.rss_feed_urls)

    @property
    def career_page_list(self) -> List[str]:
        return self.parse_csv_list(self.career_page_urls)

    @property
    def preferred_location_list(self) -> List[str]:
        return self.parse_csv_list(self.preferred_locations)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.strip())

    def ensure_directories(self) -> None:
        """Create local runtime directories if needed."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_persist_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
