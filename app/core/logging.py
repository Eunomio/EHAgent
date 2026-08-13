"""Structured logging setup with conservative default redaction."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "access_token",
    "app_secret",
    "authorization",
    "device_verify_code",
    "password",
    "secret",
    "token",
}


def _redact_sensitive_values(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact common secret fields before rendering any log event."""

    for key in list(event_dict):
        normalized = re.sub(r"[^a-z0-9]", "_", key.lower())
        if normalized in SENSITIVE_KEYS or normalized.endswith("_secret"):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str) -> None:
    """Configure standard logging and structlog at application startup."""

    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_sensitive_values,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        cache_logger_on_first_use=True,
    )
