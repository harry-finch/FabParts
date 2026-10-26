"""Bounded presentation of M5 evidence; no parser or second validation engine."""

import secrets
from collections import Counter
from typing import Any
from uuid import UUID

from kipartmanager.application.validation import LocalValidation, subject_key
from kipartmanager.domain.entities import Asset, AssetType, Collection, DomainError, Package, Part
from kipartmanager.domain.validation import Level, Qualification, ValidationReport

PAGE = 100
MEMBERS = 50


class ReportChanged(DomainError):
    pass


class ValidationReview:
    def __init__(self, validation: LocalValidation) -> None:
        self.validation = validation
        self.viewed: dict[str, tuple[str, ValidationReport]] = {}

    def subject(self, kind: str, identity: str) -> Part | Collection:
        if kind == "Part":
            return self.validation.catalogue.require(Part, UUID(identity))
        return self.validation.catalogue.require(Collection, UUID(identity))

    def resources(self, part: Part) -> dict[str, dict[str, str]]:
        catalogue = self.validation.catalogue
        owners: list[Part | Package] = [part]
        if part.package_id:
            owners.append(catalogue.require(Package, part.package_id))
        result = {}
        for owner in owners:
            for choice in catalogue.repository.choices(owner):
                asset = catalogue.require(Asset, choice.asset_id) if choice.asset_id else None
                result[choice.key] = {
                    "role": choice.asset_type.value,
                    "name": asset.name
                    if asset
                    else choice.reference.name
                    if choice.reference
                    else "",
                }
        return result

    def readiness(self, part: Part, qualification: Qualification) -> str:
        # M5 PCB eligibility is authoritative, including optional selected resources.
        if qualification.eligible:
            return "PCB"
        report = qualification.report
        if report is None or qualification.stale:
            return "INCOMPLETE"
        resources = self.resources(part)
        symbol_keys = {k for k, v in resources.items() if v["role"] == AssetType.SYMBOL.value}
        symbol_checked = any(
            f.code == "RESOURCE" and f.level is Level.PASS and f.resource_key in symbol_keys
            for f in report.findings
        )
        symbol_warnings = any(
            f.level is Level.WARNING and f.resource_key in symbol_keys for f in report.findings
        )
        deprecated = any(f.code == "DEPRECATED" for f in report.findings)
        return (
            "SCHEMATIC"
            if symbol_checked
            and not deprecated
            and (not symbol_warnings or report.warnings_accepted)
            else "INCOMPLETE"
        )

    def get(
        self, subject: Part | Collection, offset: int = 0, member_offset: int = 0
    ) -> dict[str, Any]:
        qualification = self.validation.qualification(subject)
        report = qualification.report
        current = self.validation.catalogue.require(type(subject), subject.id)
        parts = (
            [current]
            if isinstance(current, Part)
            else [
                self.validation.catalogue.require(Part, identity) for identity in current.part_ids
            ]
        )
        resources = {str(part.id): self.resources(part) for part in parts}
        counts = Counter(f.level.value for f in report.findings) if report else Counter()
        token = None
        key = subject_key(subject)
        if (
            report
            and not qualification.stale
            and any(f.level is Level.WARNING for f in report.findings)
        ):
            previous = self.viewed.get(key)
            token = previous[0] if previous and previous[1] == report else secrets.token_hex(24)
            self.viewed.pop(key, None)
            self.viewed[key] = (token, report)
            while len(self.viewed) > 32:
                self.viewed.pop(next(iter(self.viewed)))
        else:
            self.viewed.pop(key, None)
        findings = []
        for finding in report.findings[offset : offset + PAGE] if report else ():
            identity, code = str(subject.id), finding.code
            if isinstance(subject, Collection) and ":" in code:
                identity, code = code.split(":", 1)
            resource = resources.get(identity, {}).get(finding.resource_key, {})
            findings.append(
                {
                    "code": code[:256],
                    "level": finding.level.value,
                    "message": finding.message[:2048],
                    "part_id": identity if identity in resources else "",
                    "role": resource.get("role", "GLOBAL"),
                    "resource": resource.get("name", "")[:256],
                    "sha256": finding.sha256,
                }
            )
        members = []
        for part in (
            parts[member_offset : member_offset + MEMBERS]
            if isinstance(subject, Collection)
            else []
        ):
            # A collection report is its own evidence, independent of saved Part reports.
            own = (
                [f for f in report.findings if f.code.startswith(str(part.id) + ":")]
                if report
                else []
            )
            members.append(
                {
                    "id": str(part.id),
                    "name": part.name[:256],
                    "state": qualification.state
                    if qualification.state in {"UNCHECKED", "STALE"}
                    else "ERROR"
                    if any(f.level is Level.ERROR for f in own)
                    else "WARNING"
                    if any(f.level is Level.WARNING for f in own)
                    else "PASS",
                    "errors": sum(f.level is Level.ERROR for f in own),
                    "warnings": sum(f.level is Level.WARNING for f in own),
                }
            )
        return {
            "kind": type(subject).__name__,
            "id": str(subject.id),
            "name": current.name[:256],
            "state": qualification.state,
            "eligible": qualification.eligible,
            "readiness": self.readiness(current, qualification)
            if isinstance(current, Part)
            else None,
            "report": {
                "created_at": report.created_at,
                "level": report.level.value,
                "ruleset": report.ruleset,
                "warnings_accepted": report.warnings_accepted,
                "counts": {level.value: counts[level.value] for level in Level},
            }
            if report
            else None,
            "findings": findings,
            "total_findings": len(report.findings) if report else 0,
            "offset": offset,
            "members": members,
            "member_offset": member_offset,
            "total_members": len(parts) if isinstance(subject, Collection) else 0,
            "handle": token,
        }

    def run(self, subject: Part | Collection) -> dict[str, Any]:
        self.viewed.pop(subject_key(subject), None)
        self.validation.validate(subject)
        return self.get(subject)

    def accept(self, subject: Part | Collection, handle: str) -> dict[str, Any]:
        viewed = self.viewed.pop(subject_key(subject), None)
        if (
            not viewed
            or viewed[0] != handle
            or self.validation.repository.load_report(subject) != viewed[1]
        ):
            raise ReportChanged("Le rapport affiché a changé ; examiner le rapport actuel.")
        current = self.validation.qualification(subject)
        if (
            current.stale
            or current.report is None
            or not any(f.level is Level.WARNING for f in current.report.findings)
        ):
            raise ReportChanged("Le rapport affiché est obsolète ; relancer la validation.")
        # Re-evaluation and acceptance policy remain exactly those of M5.
        self.validation.validate(subject, accept_warnings=True)
        return self.get(subject)
