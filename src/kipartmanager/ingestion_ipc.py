"""Strict additive IPC v1 commands; file chunks are accessible only to the host."""

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID

from kipartmanager.application.ingestion import Ingestion, IngestionFields
from kipartmanager.domain.entities import AssetType

FIELDS: dict[str, set[str]] = {
    "ingestion_begin": {"part_id"},
    "ingestion_inspect": {"preparation", "fields"},
    "ingestion_search": {"preparation", "role", "query"},
    "ingestion_preview": {"preparation", "token"},
    "ingestion_commit": {
        "preparation",
        "operation_id",
        "fields",
        "selections",
        "action",
        "existing_id",
    },
    "ingestion_result": {"operation_id"},
    "ingestion_cancel": {"preparation"},
    "ingestion_remove": {"preparation", "handle"},
    "ingestion_file_start": {"preparation", "filename", "size"},
    "ingestion_file_chunk": {"preparation", "handle", "offset", "data"},
    "ingestion_file_finish": {"preparation", "handle", "sha256"},
    "ingestion_file_discard": {"preparation", "handle"},
}
OPTIONAL = {"part_id", "query", "action", "existing_id"}


def validate_fields(raw: object) -> IngestionFields:
    allowed = set(IngestionFields.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("Champs non reconnus.")
    values = dict(raw)
    for key, value in values.items():
        if key == "collections":
            if (
                not isinstance(value, list)
                or len(value) > 32
                or any(not isinstance(v, str) for v in value)
            ):
                raise ValueError("Liste de bibliothèques invalide.")
            for identity in value:
                UUID(identity)
            values[key] = tuple(value)
        elif not isinstance(value, str) or len(value) > 2048 or "\x00" in value:
            raise ValueError("Texte invalide ou trop long.")
        elif key == "package_id" and value:
            UUID(value)
    return IngestionFields(**values)


def validate(method: str, raw: object) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or set(raw) - FIELDS[method]
        or (FIELDS[method] - OPTIONAL) - set(raw)
    ):
        raise ValueError("Paramètres manquants ou non reconnus.")
    result = dict(raw)
    for key, value in result.items():
        if key == "fields":
            result[key] = validate_fields(value)
        elif key == "selections":
            if (
                not isinstance(value, dict)
                or set(value) - {r.value for r in AssetType}
                or len(value) > 4
            ):
                raise ValueError("Sélections invalides.")
            if any(
                not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{48}", v)
                for v in value.values()
            ):
                raise ValueError("Capacité de sélection invalide.")
        elif key in {"size", "offset"}:
            if type(value) is not int or not 0 <= value <= 16 * 1024 * 1024:
                raise ValueError("Taille ou position hors limites.")
        else:
            limit = 11000 if key == "data" else 255
            if not isinstance(value, str) or len(value) > limit or "\x00" in value:
                raise ValueError("Texte invalide ou trop long.")
            if key in {"preparation", "token", "handle"} and not re.fullmatch(
                r"[0-9a-f]{48}", value
            ):
                raise ValueError("Capacité invalide.")
            if key in {"part_id", "operation_id", "existing_id"} and value:
                UUID(value)
            if key == "role" and value not in {"SYMBOL", "FOOTPRINT", "MODEL_3D", "DATASHEET"}:
                raise ValueError("Rôle inconnu.")
            if key == "sha256" and not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("Empreinte invalide.")
    if method == "ingestion_file_chunk":
        try:
            result["data"] = base64.b64decode(result["data"], validate=True)
        except binascii.Error as error:
            raise ValueError("Bloc invalide.") from error
        if not 0 < len(result["data"]) <= 8192:
            raise ValueError("Bloc hors limites.")
    return result


def dispatch(ingestion: Ingestion, method: str, params: dict[str, Any]) -> object:
    if method == "ingestion_file_start":
        return {"handle": ingestion.files.start(**params)}
    if method == "ingestion_file_chunk":
        ingestion.files.append(**params)
        return {"received": True}
    if method == "ingestion_file_finish":
        return asdict(ingestion.files.finish(**params))
    if method == "ingestion_file_discard":
        ingestion.files.discard(**params)
        return {"discarded": True}
    handlers: dict[str, Callable[..., object]] = {
        "ingestion_begin": ingestion.begin,
        "ingestion_inspect": ingestion.inspect,
        "ingestion_search": ingestion.search,
        "ingestion_preview": ingestion.preview,
        "ingestion_commit": ingestion.commit,
        "ingestion_result": ingestion.result,
        "ingestion_cancel": ingestion.cancel,
        "ingestion_remove": ingestion.remove,
    }
    return handlers[method](**params)
