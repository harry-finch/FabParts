"""Strict global-integration IPC: native-scoped version targets, never paths."""

import re
from typing import Any
from uuid import UUID

from kipartmanager.application.kicad_integration import KiCadIntegration

METHODS = {
    f"integration_{name}"
    for name in ("get", "prepare", "activate", "verify", "recovery", "recover")
}
WRITES = METHODS - {"integration_get", "integration_verify"}


def validate(method: str, params: object) -> dict[str, Any]:
    required = {"id"}
    if method != "integration_get":
        required.add("target")
    if method == "integration_prepare":
        required.add("version")
    if method in {"integration_activate", "integration_recover"}:
        required.add("handle")
    allowed = required | ({"target"} if method == "integration_get" else set())
    if (
        method not in METHODS
        or not isinstance(params, dict)
        or not required <= set(params) <= allowed
    ):
        raise ValueError("Invalid integration parameters")
    if not isinstance(params["id"], str) or len(params["id"]) > 36:
        raise ValueError("UUID required")
    UUID(params["id"])
    if "target" in params and params["target"] not in {"6.0", "7.0", "8.0", "9.0", "10.0"}:
        raise ValueError("Unsupported KiCad target")
    if "version" in params and (
        type(params["version"]) is not int or not 1 <= params["version"] <= 999999
    ):
        raise ValueError("Invalid publication version")
    if "handle" in params and (
        not isinstance(params["handle"], str) or not re.fullmatch("[0-9a-f]{48}", params["handle"])
    ):
        raise ValueError("Reviewed operation capability required")
    return params


def dispatch(service: KiCadIntegration, method: str, params: dict[str, Any]) -> dict[str, Any]:
    operation = getattr(service, method.removeprefix("integration_"))
    result: dict[str, Any] = operation(
        **{("identity" if k == "id" else k): v for k, v in params.items()}
    )
    return result
