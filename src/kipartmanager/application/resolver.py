"""User assets, managed catalogue, then optional local KiCad; never auto-select."""

from uuid import UUID

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Package, Part
from kipartmanager.domain.resolution import (
    Candidate,
    CandidateTier,
    ResolutionResult,
    ResourceChoice,
    allowed_roles,
)
from kipartmanager.ports.resolution import ResolutionRepository


class LocalResolver:
    def __init__(
        self,
        catalogue: Catalogue,
        repository: ResolutionRepository,
        libraries: KiCadLibraries | None = None,
    ) -> None:
        self.catalogue, self.repository, self.libraries = catalogue, repository, libraries

    def owner(self, kind: type[Part] | type[Package], identity: UUID) -> Part | Package:
        return self.catalogue.require(kind, identity)

    def choices(self, owner: Part | Package) -> tuple[ResourceChoice, ...]:
        return self.repository.choices(owner)

    def search(self, owner: Part | Package, role: AssetType, text: str) -> ResolutionResult:
        owner = self.owner(type(owner), owner.id)
        if role not in allowed_roles(owner):
            raise DomainError("Rôle incompatible avec le composant ou package.")
        return self.search_candidates(role, text, owner.asset_ids)

    def search_candidates(
        self, role: AssetType, text: str, associated_ids: tuple[UUID, ...] = ()
    ) -> ResolutionResult:
        """Search without creating a persistent owner (TECH-03 preparation)."""
        candidates = []
        query = text.strip().casefold()
        for asset in self.catalogue.list_entities(Asset):
            searchable = " ".join(
                (asset.name, asset.source, asset.file.original_name if asset.file else "")
            ).casefold()
            if asset.asset_type != role or (
                query not in searchable and asset.id not in associated_ids
            ):
                continue
            unavailable = ""
            if asset.file is None:
                unavailable = "Métadonnées sans fichier géré."
            elif self.catalogue.store is None:
                unavailable = "Asset Store indisponible."
            else:
                try:
                    self.catalogue.store.verify(asset.file)
                except DomainError as error:
                    unavailable = str(error)
            candidates.append(
                Candidate(
                    CandidateTier.USER
                    if asset.origin is AssetOrigin.USER_PROVIDED
                    else CandidateTier.REMOTE
                    if asset.origin is AssetOrigin.KICAD_OFFICIAL
                    and asset.source.startswith("https://gitlab.com/kicad/libraries/")
                    else CandidateTier.MANUFACTURER
                    if asset.origin is AssetOrigin.MANUFACTURER
                    else CandidateTier.THIRD_PARTY
                    if asset.origin is AssetOrigin.TRUSTED_THIRD_PARTY
                    else CandidateTier.MANAGED,
                    ResourceChoice(role, asset_id=asset.id),
                    asset.name,
                    asset,
                    unavailable,
                )
            )
        notices: list[str] = []
        if self.libraries is not None and role is not AssetType.DATASHEET:
            try:
                report = self.libraries.report()
                notices.extend(f"{issue.source} : {issue.message}" for issue in report.issues)
                candidates.extend(
                    Candidate(
                        CandidateTier.KICAD, ResourceChoice(role, reference=ref), ref.identifier
                    )
                    for ref in self.libraries.search(text, role)
                )
            except DomainError as error:
                notices.append(str(error))
        elif role is not AssetType.DATASHEET:
            notices.append("Index KiCad indisponible ; recherche dans le catalogue uniquement.")
        candidates.sort(key=lambda c: (c.tier, c.name.casefold(), c.choice.key))
        return ResolutionResult(tuple(candidates), tuple(notices))

    def select(
        self,
        owner: Part | Package,
        candidate: Candidate,
        *,
        expected: ResourceChoice | None = None,
        replace_existing: bool = False,
    ) -> None:
        owner = self.owner(type(owner), owner.id)
        choice = candidate.choice
        if choice.asset_type not in allowed_roles(owner):
            raise DomainError("Rôle incompatible avec le composant ou package.")
        current = next((c for c in self.choices(owner) if c.asset_type == choice.asset_type), None)
        if current != expected:
            raise DomainError("La sélection a changé ; relancer la recherche.")
        if current is not None and current != choice and not replace_existing:
            raise DomainError("Confirmer explicitement le remplacement du choix actuel.")
        if candidate.unavailable:
            raise DomainError(candidate.unavailable)
        if choice.asset_id is not None:
            asset = self.catalogue.require(Asset, choice.asset_id)
            if asset != candidate.asset or asset.asset_type != choice.asset_type:
                raise DomainError("Le candidat a changé ; relancer la recherche.")
            if asset.file is None or self.catalogue.store is None:
                raise DomainError("Un fichier géré est requis pour sélectionner cet asset.")
            self.catalogue.store.verify(asset.file)
        else:
            if self.libraries is None or choice.reference is None:
                raise DomainError("Index KiCad indisponible.")
            fresh = self.libraries.reference(choice.reference.key)
            if fresh != choice.reference:
                raise DomainError("La référence indexée a changé ; reconstruire puis rechercher.")
            self.libraries.verify_reference(choice.reference)
        self.repository.choose(owner, choice, expected)
