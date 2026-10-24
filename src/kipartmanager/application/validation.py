"""Scoped reports, fresh-input invalidation and collection publication gate."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    DomainError,
    Package,
    Part,
    PartState,
)
from kipartmanager.domain.validation import (
    RULESET,
    Finding,
    Inspection,
    Level,
    Qualification,
    ValidationReport,
    connection_findings,
)
from kipartmanager.ports.validation import ResourceProbe, ValidationRepository


def subject_key(subject: Part | Collection) -> str:
    return f"{type(subject).__name__}:{subject.id.hex}"


class LocalValidation:
    def __init__(
        self, catalogue: Catalogue, probe: ResourceProbe, repository: ValidationRepository
    ) -> None:
        self.catalogue, self.probe, self.repository = catalogue, probe, repository

    def _part(self, part: Part) -> tuple[dict[str, Any], list[Finding]]:
        payload: dict[str, Any] = {"part": asdict(part), "ruleset": RULESET, "resources": []}
        findings: list[Finding] = []
        package = self.catalogue.require(Package, part.package_id) if part.package_id else None
        payload["package"] = asdict(package) if package else None
        if package is None:
            findings.append(
                Finding("PACKAGE_REQUIRED", Level.ERROR, "Package requis pour la publication PCB.")
            )
        if part.state is PartState.DEPRECATED:
            findings.append(Finding("DEPRECATED", Level.ERROR, "Composant déprécié."))
        inspections: dict[AssetType, Inspection] = {}
        for owner in (part, package):
            if owner is None:
                continue
            choices = self.catalogue.repository.choices(owner)
            payload[f"choices_{type(owner).__name__}"] = [asdict(choice) for choice in choices]
            for choice in choices:
                asset = self.catalogue.require(Asset, choice.asset_id) if choice.asset_id else None
                inspection: Inspection
                if asset:
                    if (
                        asset.file is None
                        or asset.asset_type != choice.asset_type
                        or asset.id not in owner.asset_ids
                    ):
                        inspection = Inspection(
                            choice.asset_type, error="Association ou fichier géré invalide."
                        )
                    else:
                        inspection = self.probe.managed(asset.file)
                else:
                    assert choice.reference is not None
                    inspection = self.probe.official(choice.reference)
                inspections[choice.asset_type] = inspection
                payload["resources"].append(
                    {
                        "choice": asdict(choice),
                        "asset": asdict(asset) if asset else None,
                        "inspection": asdict(inspection),
                    }
                )
                digest = (
                    asset.file.sha256
                    if asset and asset.file
                    else choice.reference.sha256
                    if choice.reference
                    else ""
                )
                findings.append(
                    Finding(
                        "RESOURCE",
                        Level.ERROR if inspection.error else Level.PASS,
                        inspection.error
                        or "Intégrité et contrôles de structure couverts satisfaits.",
                        choice.key,
                        digest,
                    )
                )
                if not inspection.error and choice.asset_type in {
                    AssetType.MODEL_3D,
                    AssetType.DATASHEET,
                }:
                    findings.append(
                        Finding(
                            "UNCOVERED",
                            Level.WARNING,
                            "Géométrie, unités et placement 3D non certifiés."
                            if choice.asset_type is AssetType.MODEL_3D
                            else "Contenu et validité PDF non certifiés ; intégrité seulement.",
                            choice.key,
                            digest,
                        )
                    )
                if asset and asset.origin in {
                    AssetOrigin.GENERATED_AI,
                    AssetOrigin.GENERATED_PARAMETRIC,
                }:
                    findings.append(
                        Finding(
                            "GENERATED_REVIEW",
                            Level.WARNING,
                            "Asset généré : révision humaine requise pour les contrôles M5.",
                            choice.key,
                            digest,
                        )
                    )
        for role in (AssetType.SYMBOL, AssetType.FOOTPRINT):
            if role not in inspections:
                findings.append(
                    Finding("CHOICE_REQUIRED", Level.ERROR, f"Choix {role.value} requis.")
                )
        symbol, footprint = inspections.get(AssetType.SYMBOL), inspections.get(AssetType.FOOTPRINT)
        if symbol and footprint and not symbol.error and not footprint.error:
            findings.extend(connection_findings(symbol, footprint))
        model = inspections.get(AssetType.MODEL_3D)
        if footprint and footprint.models and model is None:
            findings.append(
                Finding(
                    "MODEL_NOT_SELECTED",
                    Level.WARNING,
                    "Le footprint déclare des liens 3D sans modèle choisi sur le Package.",
                )
            )
        if model and footprint and not model.error and not footprint.error:
            selected = next(
                item
                for item in payload["resources"]
                if item["choice"]["asset_type"] == AssetType.MODEL_3D
            )
            choice = selected["choice"]
            name = (
                choice["reference"]["name"]
                if choice["reference"]
                else selected["asset"]["file"]["original_name"]
            )
            if footprint.models and name not in footprint.models:
                findings.append(
                    Finding(
                        "MODEL_HINT",
                        Level.WARNING,
                        "Le modèle choisi diffère des liens du footprint.",
                    )
                )
        return payload, findings

    def _evaluate(self, subject: Part | Collection) -> tuple[str, tuple[Finding, ...]]:
        current = self.catalogue.require(type(subject), subject.id)
        if isinstance(current, Part):
            payload, findings = self._part(current)
        else:
            payload = {"collection": asdict(current), "ruleset": RULESET, "parts": []}
            findings = []
            if not current.part_ids:
                findings.append(Finding("EMPTY_COLLECTION", Level.ERROR, "Collection vide."))
            for identity in current.part_ids:
                part = self.catalogue.require(Part, identity)
                part_payload, part_findings = self._part(part)
                payload["parts"].append(part_payload)
                findings.extend(
                    Finding(
                        f"{part.id}:{f.code}",
                        f.level,
                        f"{part.name} : {f.message}",
                        f.resource_key,
                        f.sha256,
                    )
                    for f in part_findings
                )
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()
        return digest, tuple(findings)

    def validate(
        self, subject: Part | Collection, *, accept_warnings: bool = False
    ) -> ValidationReport:
        fingerprint, findings = self._evaluate(subject)
        if accept_warnings:
            previous = self.repository.load_report(subject)
            if (
                previous is None
                or previous.fingerprint != fingerprint
                or previous.ruleset != RULESET
                or previous.findings != findings
            ):
                raise DomainError("Examiner un rapport actuel avant d'accepter ses WARNING.")
        report = ValidationReport(
            subject_key(subject),
            fingerprint,
            datetime.now(UTC).isoformat(),
            findings,
            accept_warnings,
        )
        self.repository.save_report(subject, report)
        return report

    def qualification(self, subject: Part | Collection) -> Qualification:
        report = self.repository.load_report(subject)
        if report is None:
            return Qualification(None)
        fingerprint, findings = self._evaluate(subject)
        return Qualification(
            report,
            report.ruleset != RULESET
            or report.fingerprint != fingerprint
            or report.findings != findings,
        )

    def require_publishable(self, collection: Collection) -> ValidationReport:
        qualification = self.qualification(collection)
        if not qualification.eligible:
            raise DomainError(
                "Collection non publiable : validation absente/obsolète, "
                "ERROR ou WARNING non accepté."
            )
        assert qualification.report is not None
        return qualification.report
