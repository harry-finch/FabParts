"""Bounded M6/M7 presentation and explicit, session-bound publication consent."""

import secrets
from dataclasses import asdict
from typing import Any
from uuid import UUID

from kipartmanager.application.publications import Publications
from kipartmanager.domain.build import BuildPlan
from kipartmanager.domain.entities import Collection, DomainError
from kipartmanager.domain.publication import Publication
from kipartmanager.domain.validation import ValidationReport

PAGE = 50


def summary(plan: BuildPlan, offset: int = 0) -> dict[str, Any]:
    return {
        "name": plan.collection_name[:256],
        "count": len(plan.parts),
        "fingerprint": plan.fingerprint,
        "library": plan.library,
        "offset": offset,
        "parts": [
            {
                "id": str(p.identity),
                "name": p.name[:256],
                "resources": [
                    {
                        "role": r.asset_type.value,
                        "name": (
                            r.file.original_name
                            if r.file
                            else r.choice.reference.name
                            if r.choice.reference
                            else ""
                        )[:256],
                        "origin": r.origin,
                    }
                    for r in p.resources
                ],
            }
            for p in plan.parts[offset : offset + PAGE]
        ],
    }


class PublicationReview:
    def __init__(self, service: Publications, scope: str = "test") -> None:
        self.service = service
        self.scope = scope
        self.viewed: dict[str, tuple[UUID, int, BuildPlan, ValidationReport]] = {}

    def collection(self, identity: str) -> Collection:
        return self.service.publisher.catalogue.require(Collection, UUID(identity))

    def history(self, identity: str, offset: int = 0) -> dict[str, Any]:
        collection = self.collection(identity)
        occupied = self.service.store.occupied_versions(collection.id)
        proposed = max(occupied, default=0) + 1
        records = sorted(
            self.service.list_publications(collection.id), key=lambda p: p.version, reverse=True
        )
        qualification = self.service.publisher.validation.qualification(collection)
        return {
            "scope": self.scope,
            "id": str(collection.id),
            "name": collection.name[:256],
            "count": len(collection.part_ids),
            "state": qualification.state,
            "eligible": qualification.eligible,
            "proposed": proposed if proposed <= 999999 else None,
            "reserved_count": len(occupied) - len(records),
            "total": len(records),
            "offset": offset,
            "versions": [
                asdict(p) | {"collection_id": str(p.collection_id), "verification": "NOT_CHECKED"}
                for p in records[offset : offset + PAGE]
            ],
        }

    def prepare(self, identity: str, offset: int = 0) -> dict[str, Any]:
        collection = self.collection(identity)
        version = max(self.service.store.occupied_versions(collection.id), default=0) + 1
        if version > 999999:
            raise DomainError("Aucun numéro de version disponible.")
        plan = self.service.publisher.plan(collection)
        report = self.service.publisher.validation.require_publishable(collection)
        viewed = (collection.id, version, plan, report)
        token = next((k for k, v in self.viewed.items() if v == viewed), None)
        if token is None:
            token = secrets.token_hex(24)
            self.viewed[token] = viewed
            while len(self.viewed) > 16:
                self.viewed.pop(next(iter(self.viewed)))
        return summary(plan, offset) | {
            "version": version,
            "handle": token,
            "level": report.level.value,
            "warnings_accepted": report.warnings_accepted,
            "warnings": sum(f.level.value == "WARNING" for f in report.findings),
            "warning_codes": sorted(
                {
                    f.code.rsplit(":", 1)[-1][:128]
                    for f in report.findings
                    if f.level.value == "WARNING"
                }
            )[:100],
        }

    def publish(self, identity: str, version: int, handle: str) -> dict[str, Any]:
        viewed = self.viewed.pop(handle, None)
        collection = self.collection(identity)
        if (
            viewed is None
            or viewed[:2] != (collection.id, version)
            or self.service.publisher.plan(collection) != viewed[2]
            or self.service.publisher.validation.require_publishable(collection) != viewed[3]
        ):
            raise DomainError("Résumé modifié ; examiner à nouveau avant de publier.")
        publication = self.service.publish(collection, version)
        return {
            "status": "COMMITTED",
            "version": publication.version,
            "fingerprint": publication.fingerprint,
            "manifest_sha256": publication.manifest_sha256,
        }

    def publication(self, identity: str, version: int) -> Publication:
        records = self.service.list_publications(UUID(identity))
        for record in records:
            if record.version == version:
                return record
        raise DomainError("Version non engagée ou absente.")

    def status(self, identity: str, version: int) -> dict[str, Any]:
        # Durable M7 evidence, including after an IPC timeout/session restart.
        if version not in self.service.store.occupied_versions(UUID(identity)):
            return {"status": "ABSENT", "version": version}
        records = self.service.list_publications(UUID(identity))
        record = next((p for p in records if p.version == version), None)
        if record is None:
            return {"status": "RESERVED", "version": version}
        return {
            "status": "COMMITTED",
            "version": version,
            "fingerprint": record.fingerprint,
            "manifest_sha256": record.manifest_sha256,
        }

    def details(self, identity: str, version: int, offset: int = 0) -> dict[str, Any]:
        record = self.publication(identity, version)
        plan, level, accepted, files = self.service.store.details(record)
        return summary(plan, offset) | {
            "version": version,
            "created_at": record.created_at,
            "manifest_sha256": record.manifest_sha256,
            "level": level,
            "warnings_accepted": accepted,
            "file_count": len(files),
            "files": list(files[:100]),
            "verification": "NOT_CHECKED",
        }

    def verify(self, identity: str, version: int) -> dict[str, Any]:
        self.service.verify(self.publication(identity, version))
        return {"version": version, "verification": "PASS"}

    def rebuild(self, identity: str, version: int, destination: str) -> dict[str, Any]:
        result = self.service.rebuild(self.publication(identity, version), destination)
        return {
            "version": version,
            "rebuilt": True,
            "library": result.library,
            "file_count": len(result.files),
        }
