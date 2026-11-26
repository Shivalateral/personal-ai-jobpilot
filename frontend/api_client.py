"""Typed HTTP client for communicating with the Personal AI JobPilot FastAPI backend."""

import os
import threading
from typing import Any, Dict, List, Optional

import httpx


class JobPilotAPIClient:
    """REST client wrapping all backend endpoints with per-thread keep-alive HTTP connection pooling."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        session_id: str = "ephemeral-default",
        username: str = "default",
    ) -> None:
        raw_url = (base_url or os.getenv("FRONTEND_API_URL", "http://127.0.0.1:8000")).strip().rstrip("/")
        if raw_url and not raw_url.startswith(("http://", "https://")):
            scheme = "http://" if (":" in raw_url or raw_url.endswith(".internal") or "localhost" in raw_url) else "https://"
            raw_url = f"{scheme}{raw_url}"
        self.base_url = raw_url
        self.auth_token = auth_token if auth_token is not None else os.getenv("API_AUTH_TOKEN", "")
        self.session_id = (session_id or "ephemeral-default").strip() or "ephemeral-default"
        self.username = (username or "default").strip() or "default"
        self.timeout = 180.0
        self._tls = threading.local()

    def _get_pool_client(self) -> httpx.Client:
        client = getattr(self._tls, "http_client", None)
        if client is None or client.is_closed:
            is_local = "127.0.0.1" in self.base_url or "localhost" in self.base_url
            client = httpx.Client(
                trust_env=not is_local,
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=16, max_connections=32),
            )
            self._tls.http_client = client
        return client

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-Session-Id": self.session_id,
            "X-User-Id": self.username,
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def get_session_status(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/session/status", timeout=20.0)

    def logout_session(self) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/session/logout", timeout=20.0)

    def get_preferences(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/profile/preferences", timeout=20.0)

    def update_preferences(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", "/api/v1/profile/preferences", json=payload, timeout=20.0)

    def verify_email(self, email_address: str) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/profile/email/verify", json={"email_address": email_address}, timeout=20.0)

    def list_users(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/users", timeout=20.0)

    def create_user(self, username: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/users", json={"username": username, "display_name": display_name or username}, timeout=20.0)

    def _client_kwargs(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        is_local = "127.0.0.1" in self.base_url or "localhost" in self.base_url
        return {
            "timeout": timeout or self.timeout,
            "headers": self._headers(),
            "trust_env": not is_local,
        }

    def _request(self, method: str, path: str, timeout: Optional[float] = None, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        client = self._get_pool_client()
        resp = client.request(
            method,
            url,
            headers=self._headers(),
            timeout=timeout or self.timeout,
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json()

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health", timeout=12.0)

    def get_overview_analytics(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/analytics/overview", timeout=45.0)

    def get_active_resume(self) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/resume/active"
        resp = self._get_pool_client().get(url, headers=self._headers(), timeout=30.0)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def upload_resume(
        self,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        persist: bool = False,
    ) -> Dict[str, Any]:
        files = {"file": (filename, file_bytes, content_type)}
        return self._request("POST", "/api/v1/resume/upload", params={"persist": persist}, files=files)

    def get_resume_utilization(self) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/resume/utilization"
        resp = self._get_pool_client().get(url, headers=self._headers(), timeout=30.0)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def activate_resume(self, resume_id: int) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/resume/{resume_id}/activate")

    def update_resume_profile(self, resume_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/v1/resume/{resume_id}", json=payload)

    def get_resume_history(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/resume/history", timeout=30.0)

    def list_jobs(self, **params) -> Dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self._request("GET", "/api/v1/jobs", params=clean, timeout=45.0)

    def get_job_detail(self, job_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/jobs/{job_id}", timeout=30.0)

    def update_application(self, job_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/v1/jobs/{job_id}/application", json=payload, timeout=30.0)

    def trigger_pipeline(self, verify_urls_live: bool = False, background: bool = False) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/pipeline/run",
            params={"background": background},
            json={"trigger_type": "manual", "verify_urls_live": verify_urls_live},
        )

    def verify_links(self, limit: int = 25) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/pipeline/verify-links", params={"limit": limit})

    def list_pipeline_runs(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/pipeline/runs", timeout=30.0)

    def get_scheduler_status(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/scheduler/status", timeout=20.0)

    def get_sources(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/pipeline/sources", timeout=20.0)

    def list_notifications(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/notifications", params={"unread_only": unread_only}, timeout=25.0)

    def mark_notification_read(self, notification_id: int) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/notifications/{notification_id}/read", timeout=20.0)

    def chat(self, message: str, session_id: str = "default", job_id: Optional[int] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/chat",
            json={"message": message, "session_id": session_id, "job_id": job_id},
            timeout=45.0,
        )

    def get_chat_history(self, session_id: str = "default") -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/chat/history", params={"session_id": session_id}, timeout=15.0)

    def clear_chat_history(self, session_id: str = "default") -> Dict[str, Any]:
        return self._request("DELETE", "/api/v1/chat/history", params={"session_id": session_id}, timeout=15.0)
