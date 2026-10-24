"""Qualify, capture current choices, and recheck before exposing build outputs."""

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.build import BuildPart, BuildPlan, BuildResource, BuildResult
from kipartmanager.domain.entities import Asset, Collection, DomainError, Package, Part
from kipartmanager.ports.publisher import LibraryBuilder


class LocalPublisher:
    def __init__(
        self, catalogue: Catalogue, validation: LocalValidation, builder: LibraryBuilder
    ) -> None:
        self.catalogue, self.validation, self.builder = catalogue, validation, builder

    def plan(self, collection: Collection) -> BuildPlan:
        report = self.validation.require_publishable(collection)
        current = self.catalogue.require(Collection, collection.id)
        parts = []
        for identity in current.part_ids:
            part = self.catalogue.require(Part, identity)
            if part.package_id is None:
                raise DomainError("Package requis pour construire une bibliothèque PCB.")
            package = self.catalogue.require(Package, part.package_id)
            resources = []
            for owner in (part, package):
                for choice in self.catalogue.repository.choices(owner):
                    if choice.asset_id:
                        asset = self.catalogue.require(Asset, choice.asset_id)
                        if asset.file is None:
                            raise DomainError("Ressource choisie sans fichier.")
                        resources.append(
                            BuildResource(choice, asset.file, asset.origin.value, asset.source)
                        )
                    else:
                        assert choice.reference is not None
                        resources.append(
                            BuildResource(
                                choice, None, "KICAD_OFFICIAL", choice.reference.identifier
                            )
                        )
            parts.append(BuildPart(part.id, part.name, package.id, tuple(resources)))
        plan = BuildPlan(current.id, current.name, report.fingerprint, tuple(parts))
        if self.validation.require_publishable(current).fingerprint != report.fingerprint:
            raise DomainError("Collection modifiée pendant la préparation ; revalider.")
        return plan

    def build(self, collection: Collection, destination: str) -> BuildResult:
        plan = self.plan(collection)

        def confirm() -> None:
            if self.plan(collection) != plan:
                raise DomainError("Collection modifiée pendant la construction ; revalider.")

        return self.builder.build(plan, destination, confirm)
