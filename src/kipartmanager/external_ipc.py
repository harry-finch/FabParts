"""Strict optional-source commands; only opaque candidates cross the UI boundary."""

import re
from typing import Any

from kipartmanager.application.external_sources import ExternalSources

METHODS = {
    "external_configuration": set(),
    "external_configure": {"source", "enabled", "revision", "domains"},
    "external_search": {"preparation", "role", "library", "query"},
    "external_download": {"preparation", "token"},
    "external_pdf": {"preparation", "url", "consent"},
    "external_status": {"preparation", "handle"},
    "external_cancel": {"preparation", "handle"},
}


def validate(method: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != METHODS[method]:
        raise ValueError("Invalid external source parameters")
    for key, value in raw.items():
        if key in {"enabled", "consent"}:
            valid = type(value) is bool
        elif key == "domains":
            valid = (
                isinstance(value, list)
                and len(value) <= 32
                and all(isinstance(v, str) and len(v) <= 253 for v in value)
            )
        else:
            valid = (
                isinstance(value, str)
                and len(value) <= (2048 if key == "url" else 255)
                and not any(ord(c) < 32 for c in value)
            )
        if not valid:
            raise ValueError("Invalid external source value")
        if key in {"preparation", "token", "handle"} and not re.fullmatch(r"[0-9a-f]{48}", value):
            raise ValueError("Invalid external capability")
    if raw.get("source", "kicad") not in {"kicad", "pdf"}:
        raise ValueError("Unknown source")
    if raw.get("role", "SYMBOL") not in {"SYMBOL", "FOOTPRINT", "MODEL_3D"}:
        raise ValueError("Unknown remote role")
    return dict(raw)


def dispatch(service: ExternalSources, method: str, params: dict[str, Any]) -> object:
    return getattr(service, method.removeprefix("external_"))(**params)
