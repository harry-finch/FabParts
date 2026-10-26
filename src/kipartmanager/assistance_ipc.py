"""Typed private M11 commands: text only, server-held consent and proposal."""

import re
from typing import Any
from uuid import UUID

from kipartmanager.application.assistance_review import AssistanceReview

METHODS = {
    "assistance_configuration": set(),
    "assistance_configure": {"enabled", "backend", "endpoint", "model"},
    "assistance_identification": {"id"},
    "assistance_prepare": {"id", "text", "include"},
    "assistance_start": {"id", "handle", "consent"},
    "assistance_status": {"id", "handle"},
    "assistance_accept": {"id", "handle", "fields", "replace_existing"},
    "assistance_cancel": {"id", "handle"},
}


def validate(method: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != METHODS[method]:
        raise ValueError("Invalid assistance parameters")
    for key, value in raw.items():
        if key in {"enabled", "include", "consent", "replace_existing"}:
            valid = type(value) is bool
        elif key == "fields":
            valid = (
                isinstance(value, list)
                and 1 <= len(value) <= 4
                and len(set(value)) == len(value)
                and all(
                    isinstance(v, str) and v in {"manufacturer", "mpn", "category", "notes"}
                    for v in value
                )
            )
        else:
            limit = {"text": 16000, "endpoint": 512, "model": 128}.get(key, 48)
            valid = isinstance(value, str) and len(value) <= limit and "\x00" not in value
        if not valid:
            raise ValueError("Invalid assistance value")
        if key == "id":
            UUID(value)
        if key == "handle" and not re.fullmatch(r"[0-9a-f]{48}", value):
            raise ValueError("Invalid assistance capability")
    if raw.get("backend", "chat") not in {"gemini", "chat", "ollama"}:
        raise ValueError("Invalid backend")
    return dict(raw)


def dispatch(service: AssistanceReview, method: str, params: dict[str, Any]) -> object:
    return getattr(service, method.removeprefix("assistance_"))(**params)
