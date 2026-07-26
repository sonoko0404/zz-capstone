from __future__ import annotations

import re
from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
_SECRET = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"password|passwd|secret|bearer token)\b\s*[:=]\s*"
    r"(?:['\"])?[^\s,;'\"]+(?:['\"])?"
)
_INTERNAL_ID = re.compile(
    r"(?i)\b(employee|customer|account|internal|armada)[-_ ]?"
    r"(id|identifier)\b\s*[:=]\s*[A-Z0-9_-]+"
)


def sanitize_public_text(value: str, *, limit: int = 20_000) -> str:
    """Redact sensitive tokens from any API/export-facing text projection."""
    value = _SSN.sub("[REDACTED SSN]", value)
    value = _CARD.sub("[REDACTED CARD NUMBER]", value)
    value = _EMAIL.sub("[REDACTED EMAIL]", value)
    value = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED SECRET]", value)
    value = _INTERNAL_ID.sub(
        lambda match: f"{match.group(1)} {match.group(2)}=[REDACTED INTERNAL ID]",
        value,
    )
    return value[:limit]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_public_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, dict):
        # Binary user attachments remain opaque. Text/chat attachments are
        # sanitized before they cross the Jira adapter or public API boundary.
        is_binary_attachment = (
            value.get("content_encoding") == "base64"
            and value.get("source") == "user"
        )
        return {
            key: (
                item
                if key == "content" and is_binary_attachment
                else _sanitize_value(item)
            )
            for key, item in value.items()
        }
    return value


def sanitize_model(model: ModelT) -> ModelT:
    """Return a type-preserving sanitized Pydantic model projection."""
    return model.__class__.model_validate(_sanitize_value(model.model_dump()))
