"""Private bounded JSON Lines protocol. stdout contains responses only."""

import json
import os
import sys
from collections.abc import Callable
from typing import Any, BinaryIO
from uuid import UUID

from kipartmanager import __version__
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.domain.entities import DomainError, PartState
from kipartmanager.infrastructure.readonly_catalogue import SCHEMA

PROTOCOL_VERSION = 1
MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 2 * 1024 * 1024


class ProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def error_response(identity: str | None, code: str, message: str) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": identity,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def validate_params(method: str, params: object) -> dict[str, Any]:
    fields = {
        "shutdown": set(),
        "health": set(),
        "list_libraries": set(),
        "get_component": {"id"},
        "list_components": {"library", "search", "limit", "offset", "category", "package", "state"},
    }
    if method not in fields:
        raise ProtocolError("UNKNOWN_METHOD", "Commande non autorisée.")
    if not isinstance(params, dict) or set(params) - fields[method]:
        raise ProtocolError("INVALID_PARAMS", "Paramètres non reconnus.")
    for key, value in params.items():
        if key in {"limit", "offset"}:
            bounds = (1, 100) if key == "limit" else (0, 1000000)
            valid = type(value) is int and bounds[0] <= value <= bounds[1]
        else:
            valid = isinstance(value, str) and len(value) <= 256 and "\x00" not in value
        if not valid:
            raise ProtocolError("INVALID_PARAMS", "Paramètre invalide ou hors limites.")
    if params.get("state") and params["state"] not in {s.value for s in PartState}:
        raise ProtocolError("INVALID_PARAMS", "État métier inconnu.")
    for key in ["id"] if method == "get_component" else []:
        try:
            UUID(params[key])
        except (ValueError, KeyError, TypeError) as error:
            raise ProtocolError("INVALID_PARAMS", "Identifiant UUID requis.") from error
    if params.get("library", "all") != "all":
        try:
            UUID(params["library"])
        except ValueError as error:
            raise ProtocolError(
                "INVALID_PARAMS", "Identifiant de bibliothèque invalide."
            ) from error
    return params


def respond(raw: bytes, reader: CatalogueReader) -> dict[str, Any]:
    identity = None
    try:
        if len(raw) > MAX_REQUEST:
            raise ProtocolError("FRAME_TOO_LARGE", "Requête trop volumineuse.")
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise ProtocolError("INVALID_JSON", "Message JSON invalide.") from error
        if not isinstance(request, dict):
            raise ProtocolError("INVALID_REQUEST", "Objet de requête requis.")
        candidate = request.get("request_id")
        if not isinstance(candidate, str) or not 1 <= len(candidate) <= 64:
            raise ProtocolError("INVALID_REQUEST", "Identifiant de requête requis (64 caractères).")
        identity = candidate
        if set(request) != {"protocol_version", "request_id", "method", "params"}:
            raise ProtocolError("INVALID_REQUEST", "Enveloppe de requête invalide.")
        if type(request["protocol_version"]) is not int or request["protocol_version"] != 1:
            raise ProtocolError("VERSION_MISMATCH", "Version de protocole incompatible.")
        method = request["method"]
        if not isinstance(method, str):
            raise ProtocolError("INVALID_REQUEST", "Nom de commande requis.")
        params = validate_params(method, request["params"])
        commands: dict[str, Callable[[], object]] = {
            "health": lambda: {
                "status": "ready",
                "engine_version": __version__,
                "protocol_version": 1,
                "catalogue_available": True,
                "schema": SCHEMA,
                "read_only": True,
                "qt_loaded": any(k.startswith("PySide6") for k in sys.modules),
                "pid": os.getpid(),
            },
            "shutdown": lambda: {"stopping": True},
            "list_libraries": reader.libraries,
            "list_components": lambda: reader.components(params),
            "get_component": lambda: reader.component(UUID(params["id"])),
        }
        result = commands[method]()
        return {"protocol_version": 1, "request_id": identity, "ok": True, "result": result}
    except ProtocolError as error:
        return error_response(identity, error.code, str(error))
    except DomainError as error:
        return error_response(identity, "DOMAIN_ERROR", str(error))
    except Exception as error:
        print(f"Catalogue read failed: {type(error).__name__}", file=sys.stderr, flush=True)
        return error_response(
            identity, "READ_FAILED", "Lecture impossible ; les données sont conservées."
        )


def serve(reader: CatalogueReader, source: BinaryIO, destination: BinaryIO) -> None:
    while raw := source.readline(MAX_REQUEST + 1):
        if len(raw) > MAX_REQUEST:
            response = error_response(None, "FRAME_TOO_LARGE", "Requête trop volumineuse.")
            destination.write(json.dumps(response).encode() + b"\n")
            destination.flush()
            return  # Do not interpret the rest of an oversized frame as another command.
        if not raw.endswith(b"\n"):
            response = error_response(None, "INVALID_REQUEST", "Message JSONL incomplet.")
        else:
            response = respond(raw, reader)
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > MAX_RESPONSE:
            encoded = json.dumps(
                error_response(
                    response["request_id"], "RESPONSE_TOO_LARGE", "Réduire la taille de la requête."
                )
            ).encode()
        destination.write(encoded + b"\n")
        destination.flush()
        if response.get("ok") and response.get("result") == {"stopping": True}:
            return
