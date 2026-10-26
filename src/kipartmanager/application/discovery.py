"""Bounded local suggestions; explicit source links are not compatibility certification."""

import re
from dataclasses import dataclass

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.documentation import MetadataField
from kipartmanager.domain.entities import Asset, AssetType, DomainError, Package, Part
from kipartmanager.domain.resolution import Candidate, CandidateTier
from kipartmanager.domain.validation import Inspection
from kipartmanager.ports.discovery import DiscoveryProbe
from kipartmanager.ports.documentation import DocumentationRepository


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True)
class Suggestion:
    candidate: Candidate
    match: str
    reason: str
    source: str
    package: str = ""


class LocalDiscovery:
    def __init__(
        self,
        catalogue: Catalogue,
        documentation: DocumentationRepository,
        resolver: LocalResolver,
        probe: DiscoveryProbe | None,
    ) -> None:
        self.catalogue, self.documentation, self.resolver, self.probe = (
            catalogue,
            documentation,
            resolver,
            probe,
        )

    def similar(self, reference: str, mpn: str) -> list[Part]:
        queries = {normalized(q) for q in (reference, mpn) if q.strip()}
        parts = []
        for part in self.catalogue.list_entities(Part):
            identity = self.documentation.identification(part.id)
            names = {normalized(part.name), normalized(identity.value(MetadataField.MPN))} - {""}
            if any(
                q == name or (len(q) >= 3 and q in name) or (len(name) >= 3 and name in q)
                for q in queries
                for name in names
            ):
                parts.append((not bool(queries & names), part.name.casefold(), str(part.id), part))
        return [p[-1] for p in sorted(parts)[:10]]

    def inspect(self, candidate: Candidate) -> Inspection | None:
        if self.probe is None or candidate.unavailable:
            return None
        choice = candidate.choice
        try:
            if candidate.asset and candidate.asset.file:
                result = self.probe.managed(candidate.asset.file)
            elif choice.reference:
                result = self.probe.official(choice.reference)
            else:
                return None
            return result if not result.error else None
        except (DomainError, OSError):
            return None

    def search(
        self,
        role: AssetType,
        reference: str,
        mpn: str,
        package_name: str,
        prior: dict[str, list[Candidate]],
    ) -> tuple[list[Suggestion], list[Part], list[str]]:
        parts = self.similar(reference, mpn)
        queries = list(dict.fromkeys(q.strip() for q in (mpn, reference) if q.strip()))
        if role is AssetType.FOOTPRINT:
            # A package term narrows a generic search, without asserting compatibility.
            queries += [q for q in package_name.split() if len(q) >= 3]
            queries += [q for q in reference.split() if q.isascii() and any(c.isdigit() for c in q)]
        found: dict[str, Suggestion] = {}
        notices: list[str] = []
        if self.resolver.libraries is None:
            notices.append("INDEX_UNAVAILABLE")
        else:
            try:
                if self.resolver.libraries.report().count == 0:
                    notices.append("INDEX_UNAVAILABLE")
            except DomainError:
                notices.append("INDEX_UNAVAILABLE")

        def add(
            candidate: Candidate, match: str, reason: str, source: str, package: str = ""
        ) -> None:
            old = found.get(candidate.choice.key)
            if old is None or (old.match == "indicative" and match != "indicative"):
                found[candidate.choice.key] = Suggestion(candidate, match, reason, source, package)

        for query in queries[:6]:
            result = self.resolver.search_candidates(role, query[:255])
            notices.extend(result.notices)
            for candidate in result.candidates[:40]:
                name = (
                    candidate.choice.reference.name
                    if candidate.choice.reference
                    else candidate.name
                )
                exact = normalized(name) in {normalized(reference), normalized(mpn)} - {""}
                add(candidate, "exact" if exact else "indicative", "name_match", candidate.name)
        for part in parts:
            owners: list[Part | Package] = [part]
            package = self.catalogue.require(Package, part.package_id) if part.package_id else None
            if package:
                owners.append(package)
            for owner in owners:
                for choice in self.catalogue.repository.choices(owner):
                    if choice.asset_type is not role:
                        continue
                    # Reuse resolver verification/provenance for managed bytes as well.
                    if choice.asset_id:
                        candidates = self.resolver.search_candidates(role, "", (choice.asset_id,))
                        related = next(
                            (c for c in candidates.candidates if c.choice == choice), None
                        )
                    else:
                        assert choice.reference is not None
                        related = Candidate(
                            CandidateTier.KICAD, choice, choice.reference.identifier
                        )
                    if related:
                        add(
                            related,
                            "declared",
                            "catalogue_choice",
                            part.name,
                            package.name if package else "",
                        )
            if role is AssetType.DATASHEET:
                for document in self.documentation.documents(part.id):
                    asset = self.catalogue.require(Asset, document.asset_id)
                    result = self.resolver.search_candidates(role, asset.name, (asset.id,))
                    for candidate in result.candidates:
                        if candidate.choice.asset_id == asset.id:
                            add(candidate, "declared", "catalogue_document", part.name)

        # Follow exact identifiers, including inherited symbol Footprint properties.
        if role is AssetType.FOOTPRINT:
            for symbol in prior.get("SYMBOL", [])[:4]:
                info = self.inspect(symbol)
                if info and info.footprint:
                    result = self.resolver.search_candidates(
                        role, info.footprint.rsplit(":", 1)[-1][:255]
                    )
                    notices.extend(result.notices)
                    for candidate in result.candidates:
                        ref = candidate.choice.reference
                        if ref and ref.identifier == info.footprint:
                            footprint_info = self.inspect(candidate)
                            if footprint_info and set(info.numbers) == set(footprint_info.numbers):
                                add(
                                    candidate, "declared", "symbol_footprint", symbol.name, ref.name
                                )
        if role is AssetType.MODEL_3D:
            for footprint in prior.get("FOOTPRINT", [])[:8]:
                info = self.inspect(footprint)
                if info is None:
                    continue
                if self.probe is None:
                    continue
                try:
                    links = self.probe.model_links(
                        footprint.asset.file if footprint.asset else None,
                        footprint.choice.reference,
                    )
                except (DomainError, OSError, UnicodeError):
                    continue
                for link in links:
                    match = re.fullmatch(r"\$\{KICAD(?:\d+)?_3DMODEL_DIR\}/([^{}]+)", link)
                    if not match:
                        continue
                    path = match[1]
                    if any(p in {"", ".", ".."} for p in path.split("/")):
                        continue
                    result = self.resolver.search_candidates(role, path.rsplit("/", 1)[-1])
                    for candidate in result.candidates:
                        ref = candidate.choice.reference
                        if ref and ref.relative_path == path:
                            add(candidate, "declared", "footprint_model", footprint.name)
        ordered = sorted(
            found.values(),
            key=lambda s: (
                s.match == "indicative",
                s.candidate.tier,
                s.candidate.name.casefold(),
                s.candidate.choice.key,
            ),
        )[:40]
        return ordered, parts, list(dict.fromkeys(notices))
