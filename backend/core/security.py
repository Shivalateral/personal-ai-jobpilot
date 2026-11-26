"""Security utilities: Fernet encryption for resume PII/raw content and token helpers."""

import hashlib
import hmac
import logging
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import DATA_DIR, get_settings

logger = logging.getLogger(__name__)


def _load_or_create_fernet_key() -> bytes:
    """Load RESUME_ENCRYPTION_KEY from settings or persist a dev key locally."""
    settings = get_settings()
    if settings.resume_encryption_key:
        return settings.resume_encryption_key.encode("utf-8")

    key_path: Path = DATA_DIR / ".fernet.key"
    if key_path.exists():
        return key_path.read_bytes().strip()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    logger.warning(
        "RESUME_ENCRYPTION_KEY not set; generated local development key at %s",
        key_path.name,
    )
    return key


class ResumeVault:
    """Encrypts and decrypts sensitive resume text before database persistence."""

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._key = key or _load_or_create_fernet_key()
        self._fernet = Fernet(self._key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt UTF-8 plaintext into a URL-safe base64 token string."""
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt token string back to plaintext; raises ValueError on tampering."""
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt stored resume content with current key.") from exc


def sha256_digest(data: bytes) -> str:
    """Compute SHA-256 hex digest for resume deduplication and integrity checks."""
    return hashlib.sha256(data).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison for auth tokens."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
