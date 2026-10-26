"""Strict additive IPC commands. Destination is supplied only by the native host."""

import re
from typing import Any
from uuid import UUID

from kipartmanager.application.publication_review import PublicationReview

METHODS = {
    "publication_history",
    "publication_prepare",
    "publication_publish",
    "publication_status",
    "publication_details",
    "publication_verify",
    "publication_rebuild",
}
WRITES = {"publication_publish", "publication_rebuild"}


def validate(method: str, params: object) -> dict[str, Any]:
    required = {"id"}
    if method not in {"publication_history", "publication_prepare"}:
        required.add("version")
    if method == "publication_publish":
        required.add("handle")
    if method == "publication_rebuild":
        required.add("destination")
    allowed = required | (
        {"offset"}
        if method in {"publication_history", "publication_prepare", "publication_details"}
        else set()
    )
    if (
        method not in METHODS
        or not isinstance(params, dict)
        or not required <= set(params) <= allowed
    ):
        raise ValueError("Invalid publication parameters")
    if not isinstance(params["id"], str) or len(params["id"]) > 36:
        raise ValueError("UUID required")
    UUID(params["id"])
    if "version" in params and (
        type(params["version"]) is not int or not 1 <= params["version"] <= 999999
    ):
        raise ValueError("Invalid version")
    if "offset" in params and (
        type(params["offset"]) is not int or not 0 <= params["offset"] <= 1000000
    ):
        raise ValueError("Invalid offset")
    if "handle" in params and (
        not isinstance(params["handle"], str) or not re.fullmatch(r"[0-9a-f]{48}", params["handle"])
    ):
        raise ValueError("Summary capability required")
    if "destination" in params and (
        not isinstance(params["destination"], str)
        or not 1 <= len(params["destination"]) <= 4096
        or "\x00" in params["destination"]
    ):
        raise ValueError("Native destination required")
    return params


def dispatch(review: PublicationReview, method: str, params: dict[str, Any]) -> dict[str, Any]:
    operation = getattr(review, method.removeprefix("publication_"))
    arguments = {("identity" if k == "id" else k): v for k, v in params.items()}
    result: dict[str, Any] = operation(**arguments)
    return result
