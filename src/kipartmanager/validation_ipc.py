"""Strict additive IPC v1 validation commands, without report mutation payloads."""

import re
from typing import Any
from uuid import UUID

from kipartmanager.application.validation_review import ValidationReview

METHODS = {"validation_get", "validation_run", "validation_accept"}
WRITES = {"validation_run", "validation_accept"}


def validate(method: str, params: object) -> dict[str, Any]:
    required = {"kind", "id"} | ({"handle"} if method == "validation_accept" else set())
    allowed = required | ({"offset", "member_offset"} if method == "validation_get" else set())
    if (
        method not in METHODS
        or not isinstance(params, dict)
        or not required <= set(params) <= allowed
    ):
        raise ValueError("Invalid validation parameters")
    if params["kind"] not in ("Part", "Collection"):
        raise ValueError("Invalid subject kind")
    try:
        if not isinstance(params["id"], str) or len(params["id"]) > 36:
            raise ValueError
        UUID(params["id"])
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("UUID required") from error
    for name in ("offset", "member_offset"):
        if name in params and (type(params[name]) is not int or not 0 <= params[name] <= 1000000):
            raise ValueError("Invalid page offset")
    if method == "validation_accept" and (
        not isinstance(params["handle"], str) or not re.fullmatch(r"[0-9a-f]{48}", params["handle"])
    ):
        raise ValueError("Viewed report capability required")
    return params


def dispatch(review: ValidationReview, method: str, params: dict[str, Any]) -> dict[str, Any]:
    subject = review.subject(params["kind"], params["id"])
    if method == "validation_get":
        return review.get(subject, params.get("offset", 0), params.get("member_offset", 0))
    if method == "validation_run":
        return review.run(subject)
    return review.accept(subject, params["handle"])
