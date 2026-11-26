"""Structured logging configuration with PII and credential redaction."""

import logging
import re
import sys


_SENSITIVE_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9_-]{10,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(gsk_[A-Za-z0-9_-]{10,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(AQ\.[A-Za-z0-9_-]{10,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(AIza[A-Za-z0-9_-]{10,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"), "[REDACTED_EMAIL]"),
]


class SensitiveDataFilter(logging.Filter):
    """Filter that masks potential secrets or personal emails in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, replacement in _SENSITIVE_PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure application-wide structured logging."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.addFilter(SensitiveDataFilter())

    # Reduce noise from third-party libraries
    for noisy in ("httpx", "chromadb", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
