"""Private bounded JSON Lines protocol. stdout contains responses only."""

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

from kipartmanager import __version__
from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.assistance_review import AssistanceReview
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.external_sources import ExternalSources
from kipartmanager.application.ingestion import Ingestion
from kipartmanager.application.kicad_integration import KiCadIntegration
from kipartmanager.application.publication_review import PublicationReview
from kipartmanager.application.validation_review import ReportChanged, ValidationReview
from kipartmanager.assistance_ipc import METHODS as ASSISTANCE_METHODS
from kipartmanager.assistance_ipc import (
    dispatch as dispatch_assistance,
)
from kipartmanager.assistance_ipc import (
    validate as validate_assistance,
)
from kipartmanager.domain.entities import DomainError, PartState
from kipartmanager.external_ipc import METHODS as EXTERNAL_METHODS
from kipartmanager.external_ipc import dispatch as dispatch_external
from kipartmanager.external_ipc import validate as validate_external
from kipartmanager.infrastructure.ingestion_sandbox import checked_root
from kipartmanager.infrastructure.readonly_catalogue import SCHEMA
from kipartmanager.infrastructure.user_workspace import UserWorkspace
from kipartmanager.ingestion_ipc import FIELDS as INGESTION_METHODS
from kipartmanager.ingestion_ipc import dispatch
from kipartmanager.ingestion_ipc import validate as validate_ingestion
from kipartmanager.integration_ipc import METHODS as INTEGRATION_METHODS
from kipartmanager.integration_ipc import WRITES as INTEGRATION_WRITES
from kipartmanager.integration_ipc import dispatch as dispatch_integration
from kipartmanager.integration_ipc import validate as validate_integration
from kipartmanager.ports.previews import PDF_LIMIT
from kipartmanager.publication_ipc import METHODS as PUBLICATION_METHODS
from kipartmanager.publication_ipc import WRITES as PUBLICATION_WRITES
from kipartmanager.publication_ipc import dispatch as dispatch_publication
from kipartmanager.publication_ipc import validate as validate_publication
from kipartmanager.validation_ipc import METHODS as VALIDATION_METHODS
from kipartmanager.validation_ipc import WRITES as VALIDATION_WRITES
from kipartmanager.validation_ipc import dispatch as dispatch_validation
from kipartmanager.validation_ipc import validate as validate_validation

PROTOCOL_VERSION = 1
MAX_REQUEST = 16 * 1024
# Only assistance_prepare may carry 16 000 Unicode characters (including JSON escapes).
MAX_ASSISTANCE_REQUEST = 256 * 1024
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
        "get_asset_preview": {"id", "role", "asset_id"},
        "read_pdf_chunk": {"handle", "offset"},
        "release_preview": {"handle"},
        "get_model_status": {"handle"},
        "read_mesh_chunk": {"handle", "offset"},
        "release_model_preview": {"handle"},
        "list_components": {"library", "search", "limit", "offset", "category", "package", "state"},
    }
    if method not in fields:
        raise ProtocolError("UNKNOWN_METHOD", "Commande non autorisée.")
    if not isinstance(params, dict) or set(params) - fields[method]:
        raise ProtocolError("INVALID_PARAMS", "Paramètres non reconnus.")
    for key, value in params.items():
        if method in {"read_pdf_chunk", "read_mesh_chunk"} and key == "offset":
            valid = type(value) is int and 0 <= value < PDF_LIMIT and value % 65536 == 0
        elif key in {"limit", "offset"}:
            bounds = (1, 100) if key == "limit" else (0, 1000000)
            valid = type(value) is int and bounds[0] <= value <= bounds[1]
        else:
            valid = isinstance(value, str) and len(value) <= 256 and "\x00" not in value
        if not valid:
            raise ProtocolError("INVALID_PARAMS", "Paramètre invalide ou hors limites.")
    if params.get("state") and params["state"] not in {s.value for s in PartState}:
        raise ProtocolError("INVALID_PARAMS", "État métier inconnu.")
    for key in (
        (["id"] + (["asset_id"] if params.get("asset_id") else []))
        if method in {"get_component", "get_asset_preview"}
        else []
    ):
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
    if method == "get_asset_preview" and params.get("role") not in {
        "SYMBOL",
        "FOOTPRINT",
        "DATASHEET",
        "MODEL_3D",
    }:
        raise ProtocolError("INVALID_PARAMS", "Rôle de ressource requis.")
    if method in {
        "read_pdf_chunk",
        "release_preview",
        "read_mesh_chunk",
        "get_model_status",
        "release_model_preview",
    } and not re.fullmatch(r"[0-9a-f]{48}", params.get("handle", "")):
        raise ProtocolError("INVALID_PARAMS", "Handle PDF invalide.")
    if method in {"read_pdf_chunk", "read_mesh_chunk"} and "offset" not in params:
        raise ProtocolError("INVALID_PARAMS", "Position de bloc requise.")
    return params


def respond(
    raw: bytes,
    reader: CatalogueReader,
    previews: AssetPreviews | None = None,
    ingestion: Ingestion | None = None,
    schema: str = SCHEMA,
    workspace: UserWorkspace | None = None,
    review: ValidationReview | None = None,
    publications: PublicationReview | None = None,
    integration: KiCadIntegration | None = None,
    external: ExternalSources | None = None,
    assistance: AssistanceReview | None = None,
) -> dict[str, Any]:
    identity = None
    try:
        if len(raw) > MAX_ASSISTANCE_REQUEST:
            raise ProtocolError("FRAME_TOO_LARGE", "Requête trop volumineuse.")
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            if len(raw) > MAX_REQUEST:
                raise ProtocolError("FRAME_TOO_LARGE", "Requête trop volumineuse.") from error
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
        if len(raw) > MAX_REQUEST and method != "assistance_prepare":
            raise ProtocolError("FRAME_TOO_LARGE", "Requête trop volumineuse.")
        if method in ASSISTANCE_METHODS:
            if (
                ingestion is None
                or assistance is None
                or bool(workspace and workspace.requires_restart)
            ):
                raise ProtocolError("READ_ONLY", "Assistance unavailable in this session")
            if ingestion.preparation is not None:
                raise ProtocolError("BUSY", "Finish the active preparation first")
            try:
                params = validate_assistance(method, request["params"])
            except (ValueError, TypeError, AttributeError) as error:
                raise ProtocolError("INVALID_PARAMS", "Invalid assistance parameters") from error
            return {
                "protocol_version": 1,
                "request_id": identity,
                "ok": True,
                "result": dispatch_assistance(assistance, method, params),
            }
        if method in EXTERNAL_METHODS:
            if (
                ingestion is None
                or external is None
                or bool(workspace and workspace.requires_restart)
            ):
                raise ProtocolError("READ_ONLY", "External sources unavailable in this session")
            try:
                params = validate_external(method, request["params"])
            except (ValueError, TypeError) as error:
                raise ProtocolError("INVALID_PARAMS", str(error)) from error
            return {
                "protocol_version": 1,
                "request_id": identity,
                "ok": True,
                "result": dispatch_external(external, method, params),
            }
        if method in INTEGRATION_METHODS:
            if integration is None:
                raise ProtocolError("READ_FAILED", "Integration unavailable")
            if method in INTEGRATION_WRITES and (
                ingestion is None or bool(workspace and workspace.requires_restart)
            ):
                raise ProtocolError("READ_ONLY", "Integration writes unavailable")
            if ingestion is not None and ingestion.preparation is not None:
                raise ProtocolError("BUSY", "Finish the active preparation first")
            try:
                params = validate_integration(method, request["params"])
            except (ValueError, TypeError, AttributeError) as error:
                raise ProtocolError("INVALID_PARAMS", str(error)) from error
            try:
                integration_result = dispatch_integration(integration, method, params)
            except OSError as error:
                raise ProtocolError(
                    "INTEGRATION_IO", error.strerror or type(error).__name__
                ) from error
            return {
                "protocol_version": 1,
                "request_id": identity,
                "ok": True,
                "result": integration_result,
            }
        if method in PUBLICATION_METHODS:
            if publications is None:
                raise ProtocolError("READ_FAILED", "Publications unavailable")
            if method in PUBLICATION_WRITES and (
                ingestion is None or bool(workspace and workspace.requires_restart)
            ):
                raise ProtocolError("READ_ONLY", "Publication writes unavailable")
            if ingestion is not None and ingestion.preparation is not None:
                raise ProtocolError("BUSY", "Finish the active preparation first")
            try:
                params = validate_publication(method, request["params"])
            except (ValueError, TypeError, AttributeError) as error:
                raise ProtocolError("INVALID_PARAMS", str(error)) from error
            if method == "publication_rebuild":
                target = checked_root(Path(params["destination"]))
                if workspace and target.is_relative_to(workspace.home.resolve()):
                    raise DomainError("Destination dans le workspace personnel interdite.")
            publication_result = dispatch_publication(publications, method, params)
            return {
                "protocol_version": 1,
                "request_id": identity,
                "ok": True,
                "result": publication_result,
            }
        if method in VALIDATION_METHODS:
            if review is None:
                raise ProtocolError("READ_FAILED", "Validation unavailable")
            if method in VALIDATION_WRITES and (
                ingestion is None or bool(workspace and workspace.requires_restart)
            ):
                raise ProtocolError("READ_ONLY", "Validation writes unavailable")
            if ingestion is not None and ingestion.preparation is not None:
                raise ProtocolError("BUSY", "Finish the active preparation first")
            try:
                params = validate_validation(method, request["params"])
            except (ValueError, TypeError) as error:
                raise ProtocolError("INVALID_PARAMS", str(error)) from error
            result: object = dispatch_validation(review, method, params)
            return {"protocol_version": 1, "request_id": identity, "ok": True, "result": result}
        if method.startswith("workspace_"):
            if workspace is None:
                raise ProtocolError("READ_ONLY", "Personal workspace required")
            if ingestion is not None and ingestion.preparation is not None:
                raise ProtocolError("BUSY", "Finish the active preparation first")
            fields = {
                "workspace_info": set(),
                "workspace_backup": set(),
                "workspace_verify": {"path"},
                "workspace_restore": {"handle"},
            }
            params = request["params"]
            if (
                method not in fields
                or not isinstance(params, dict)
                or set(params) != fields[method]
                or any(
                    not isinstance(v, str) or not v or len(v) > 4096 or "\x00" in v
                    for v in params.values()
                )
            ):
                raise ProtocolError("INVALID_PARAMS", "Invalid workspace command")
            operations = {
                "workspace_info": lambda: workspace.info(),
                "workspace_backup": lambda: workspace.backup(),
                "workspace_verify": lambda: workspace.verify(Path(params["path"])),
                "workspace_restore": lambda: workspace.restore(params["handle"]),
            }
            if assistance and method == "workspace_restore":
                assistance.close()
            result = operations[method]()
            return {"protocol_version": 1, "request_id": identity, "ok": True, "result": result}
        if method in INGESTION_METHODS:
            if workspace is not None and workspace.requires_restart:
                raise ProtocolError("READ_ONLY", "Restart required after restore")
            if ingestion is None:
                raise ProtocolError("READ_ONLY", "Cette session est ouverte en lecture seule.")
            try:
                params = validate_ingestion(method, request["params"])
            except (ValueError, TypeError) as error:
                raise ProtocolError("INVALID_PARAMS", str(error)) from error
            if assistance and method == "ingestion_begin":
                assistance.close()
            if external and method in {"ingestion_begin", "ingestion_cancel", "ingestion_commit"}:
                external.close()
            result = dispatch(ingestion, method, params)
            return {"protocol_version": 1, "request_id": identity, "ok": True, "result": result}
        params = validate_params(method, request["params"])
        commands: dict[str, Callable[[], object]] = {
            "health": lambda: {
                "status": "ready",
                "engine_version": __version__,
                "protocol_version": 1,
                "catalogue_available": True,
                "schema": schema,
                "read_only": ingestion is None or bool(workspace and workspace.requires_restart),
                "workspace_mode": "personal"
                if workspace
                else "sandbox"
                if ingestion
                else "readonly",
                "qt_loaded": any(k.startswith("PySide6") for k in sys.modules),
                "pid": os.getpid(),
            },
            "shutdown": lambda: {"stopping": True},
            "list_libraries": reader.libraries,
            "list_components": lambda: reader.components(params),
            "get_component": lambda: reader.component(UUID(params["id"])),
        }
        if previews is not None:
            commands.update(
                {
                    "get_asset_preview": lambda: previews.get(**params),
                    "read_pdf_chunk": lambda: previews.chunk(**params),
                    "release_preview": lambda: previews.release(**params),
                }
            )
        if previews is not None and previews.models is not None:
            models = previews.models
            commands.update(
                {
                    "get_model_status": lambda: models.status(**params),
                    "read_mesh_chunk": lambda: models.chunk(**params),
                    "release_model_preview": lambda: models.release(**params),
                }
            )
        if method not in commands:
            raise ProtocolError("READ_FAILED", "Service d’aperçu indisponible.")
        result = commands[method]()
        return {"protocol_version": 1, "request_id": identity, "ok": True, "result": result}
    except ProtocolError as error:
        return error_response(identity, error.code, str(error))
    except ReportChanged as error:
        return error_response(identity, "REPORT_CHANGED", str(error))
    except DomainError as error:
        return error_response(identity, "DOMAIN_ERROR", str(error))
    except Exception as error:
        print(f"Catalogue read failed: {type(error).__name__}", file=sys.stderr, flush=True)
        return error_response(
            identity, "READ_FAILED", "Lecture impossible ; les données sont conservées."
        )


def serve(
    reader: CatalogueReader,
    source: BinaryIO,
    destination: BinaryIO,
    previews: AssetPreviews | None = None,
    ingestion: Ingestion | None = None,
    schema: str = SCHEMA,
    workspace: UserWorkspace | None = None,
    review: ValidationReview | None = None,
    publications: PublicationReview | None = None,
    integration: KiCadIntegration | None = None,
    external: ExternalSources | None = None,
    assistance: AssistanceReview | None = None,
) -> None:
    while raw := source.readline(MAX_ASSISTANCE_REQUEST + 1):
        if len(raw) > MAX_ASSISTANCE_REQUEST:
            response = error_response(None, "FRAME_TOO_LARGE", "Requête trop volumineuse.")
            destination.write(json.dumps(response).encode() + b"\n")
            destination.flush()
            return  # Do not interpret the rest of an oversized frame as another command.
        if not raw.endswith(b"\n"):
            response = error_response(None, "INVALID_REQUEST", "Message JSONL incomplet.")
        else:
            response = respond(
                raw,
                reader,
                previews,
                ingestion,
                schema,
                workspace,
                review,
                publications,
                integration,
                external,
                assistance,
            )
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > MAX_RESPONSE:
            encoded = json.dumps(
                error_response(
                    response["request_id"], "RESPONSE_TOO_LARGE", "Réduire la taille de la requête."
                )
            ).encode()
        destination.write(encoded + b"\n")
        destination.flush()
        if response.get("error", {}).get("code") == "FRAME_TOO_LARGE":
            return
        if response.get("ok") and response.get("result") == {"stopping": True}:
            return
