"""Versioned portable JSON encoding; no installation paths or current-data reads."""

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.build import BuildPart, BuildPlan, BuildResource
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.domain.publication import BUILDER_VERSION, MANIFEST_VERSION, PublicationSnapshot
from kipartmanager.domain.resolution import ResourceChoice


def canonical(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def encode_plan(plan: BuildPlan) -> dict[str, Any]:
    return {
        "collection_id": str(plan.collection_id),
        "collection_name": plan.collection_name,
        "fingerprint": plan.fingerprint,
        "parts": [
            {
                "id": str(part.identity),
                "name": part.name,
                "package_id": str(part.package_id),
                "resources": [
                    {
                        "role": resource.asset_type.value,
                        "asset_id": str(resource.choice.asset_id)
                        if resource.choice.asset_id
                        else None,
                        "reference": asdict(resource.choice.reference)
                        if resource.choice.reference
                        else None,
                        "file": asdict(resource.file) if resource.file else None,
                        "origin": resource.origin,
                    }
                    for resource in part.resources
                ],
            }
            for part in plan.parts
        ],
    }


def decode_plan(data: dict[str, Any]) -> BuildPlan:
    parts = []
    for part in data["parts"]:
        resources = []
        for resource in part["resources"]:
            ref = resource["reference"]
            reference = (
                KiCadReference(**{**ref, "asset_type": AssetType(ref["asset_type"])})
                if ref
                else None
            )
            choice = ResourceChoice(
                AssetType(resource["role"]),
                UUID(resource["asset_id"]) if resource["asset_id"] else None,
                reference,
            )
            resources.append(
                BuildResource(
                    choice,
                    AssetFile(**resource["file"]) if resource["file"] else None,
                    resource["origin"],
                    choice.key,
                )
            )
        parts.append(
            BuildPart(UUID(part["id"]), part["name"], UUID(part["package_id"]), tuple(resources))
        )
    return BuildPlan(
        UUID(data["collection_id"]), data["collection_name"], data["fingerprint"], tuple(parts)
    )


def manifest_base(snapshot: PublicationSnapshot, version: int, created_at: str) -> dict[str, Any]:
    report = snapshot.validation
    if not report.eligible or report.fingerprint != snapshot.plan.fingerprint:
        raise DomainError("Instantané non qualifié pour publication.")
    return {
        "schema": MANIFEST_VERSION,
        "builder": BUILDER_VERSION,
        "version": version,
        "created_at": created_at,
        "plan": encode_plan(snapshot.plan),
        "validation": {
            "subject_key": report.subject_key,
            "fingerprint": report.fingerprint,
            "ruleset": report.ruleset,
            "created_at": report.created_at,
            "level": report.level.value,
            "warnings_accepted": report.warnings_accepted,
            "findings": [
                {"code": f.code, "level": f.level.value, "key": f.resource_key, "sha256": f.sha256}
                for f in report.findings
            ],
        },
    }
