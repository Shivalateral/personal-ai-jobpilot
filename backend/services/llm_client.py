"""Configurable OpenAI-compatible LLM client with Gemini support, retry, and quota circuit breaker."""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Fault-tolerant OpenAI-compatible LLM wrapper (Gemini, OpenAI, Ollama, Groq)."""

    # Class-level circuit breaker shared across requests to avoid repeated timeout delays
    _last_status: str = "unknown"
    _last_error: str = ""
    _cooldown_until: float = 0.0

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.fallback_base_url = settings.llm_fallback_base_url or "https://api.openai.com/v1"
        self.fallback_api_key = settings.llm_fallback_api_key
        self.fallback_model = settings.llm_fallback_model or "gpt-4o-mini"
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.timeout = settings.llm_timeout_seconds if timeout is None else timeout
        self._client: Optional[OpenAI] = None
        self._fallback_client: Optional[OpenAI] = None

    @property
    def is_available(self) -> bool:
        """Return True if primary or fallback API key is configured and not in quota cooldown."""
        has_primary = bool(self.api_key and self.api_key.strip())
        has_fallback = bool(self.fallback_api_key and self.fallback_api_key.strip())
        if not (has_primary or has_fallback):
            return False
        if time.monotonic() < LLMClient._cooldown_until and not has_fallback:
            return False
        return True

    def status_summary(self) -> Dict[str, Any]:
        """Return safe non-secret LLM configuration and runtime status."""
        configured = bool(self.api_key and self.api_key.strip())
        if not configured:
            status = "unconfigured"
        elif time.monotonic() < LLMClient._cooldown_until:
            status = LLMClient._last_status or "cooldown"
        elif LLMClient._last_status in ("connected", "quota_exhausted", "auth_error"):
            status = LLMClient._last_status
        else:
            status = "configured"
        return {
            "configured": configured or bool(self.fallback_api_key and self.fallback_api_key.strip()),
            "status": status,
            "provider": get_settings().llm_provider,
            "model": self.model,
            "base_url": self.base_url,
            "fallback_configured": bool(self.fallback_api_key and self.fallback_api_key.strip()),
            "fallback_model": self.fallback_model if (self.fallback_api_key and self.fallback_api_key.strip()) else "",
            "last_error": LLMClient._last_error if status != "connected" else "",
        }

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=min(12.0, float(self.timeout)),
                max_retries=0,
            )
        return self._client

    def _get_fallback_client(self) -> Optional[OpenAI]:
        if not (self.fallback_api_key and self.fallback_api_key.strip()):
            return None
        if self._fallback_client is None:
            self._fallback_client = OpenAI(
                base_url=self.fallback_base_url,
                api_key=self.fallback_api_key,
                timeout=min(12.0, float(self.timeout)),
                max_retries=0,
            )
        return self._fallback_client

    def _handle_error(self, exc: Exception) -> None:
        msg = str(exc)
        lower = msg.lower()
        if "insufficient_quota" in lower or "credit_balance_exhausted" in lower or "exceeded your current quota" in lower or "429" in lower:
            LLMClient._last_status = "quota_exhausted"
            LLMClient._last_error = "API quota/credits exhausted; using deterministic fallback."
            LLMClient._cooldown_until = time.monotonic() + 300.0
        elif "401" in lower or "unauthorized" in lower or "api_key_invalid" in lower:
            LLMClient._last_status = "auth_error"
            LLMClient._last_error = "Invalid LLM API credentials."
            LLMClient._cooldown_until = time.monotonic() + 300.0
        elif "503" in lower or "unavailable" in lower:
            LLMClient._last_status = "transient_unavailable"
            LLMClient._last_error = "LLM endpoint temporarily busy (503)."
            LLMClient._cooldown_until = time.monotonic() + 20.0
        else:
            LLMClient._last_status = "error"
            LLMClient._last_error = msg[:160]
            LLMClient._cooldown_until = time.monotonic() + 30.0
        logger.warning("LLM request failed (%s); falling back to deterministic mode.", msg[:180])

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 900) -> Optional[str]:
        """Execute a chat completion with automatic Gemini -> secondary provider fallback."""
        if not self.is_available:
            return None

        last_exc: Optional[Exception] = None
        if self.api_key and self.api_key.strip() and time.monotonic() >= LLMClient._cooldown_until:
            client = self._get_client()
            candidate_models = [self.model]
            if "generativelanguage.googleapis.com" in self.base_url:
                if "gemini-3.5-flash" not in candidate_models:
                    candidate_models.append("gemini-3.5-flash")

            for model_name in candidate_models:
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=max_tokens,
                    )
                    content = response.choices[0].message.content
                    LLMClient._last_status = "connected"
                    LLMClient._last_error = ""
                    LLMClient._cooldown_until = 0.0
                    return content.strip() if content else None
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc)
                    if "503" in msg or "UNAVAILABLE" in msg or "404" in msg:
                        continue
                    break

        fb_client = self._get_fallback_client()
        if fb_client is not None:
            try:
                response = fb_client.chat.completions.create(
                    model=self.fallback_model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                LLMClient._last_status = "connected"
                LLMClient._last_error = ""
                return content.strip() if content else None
            except Exception as fb_exc:
                last_exc = fb_exc

        if last_exc is not None:
            self._handle_error(last_exc)
        return None

    def chat_json(self, messages: List[Dict[str, str]], max_tokens: int = 1200) -> Optional[Dict[str, Any]]:
        """Request a JSON-formatted LLM completion with Gemini -> secondary OpenAI fallback."""
        if not self.is_available:
            return None

        last_exc: Optional[Exception] = None
        if self.api_key and self.api_key.strip() and time.monotonic() >= LLMClient._cooldown_until:
            try:
                client = self._get_client()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                raw = (response.choices[0].message.content or "").strip()
                if raw:
                    LLMClient._last_status = "connected"
                    LLMClient._last_error = ""
                    LLMClient._cooldown_until = 0.0
                    return json.loads(raw)
            except Exception as exc:
                last_exc = exc

        fb_client = self._get_fallback_client()
        if fb_client is not None:
            try:
                response = fb_client.chat.completions.create(
                    model=self.fallback_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                raw = (response.choices[0].message.content or "").strip()
                if raw:
                    LLMClient._last_status = "connected"
                    LLMClient._last_error = ""
                    return json.loads(raw)
            except Exception as fb_exc:
                last_exc = fb_exc

        if last_exc is not None:
            self._handle_error(last_exc)
        return None
