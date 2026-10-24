"""Bounded read projection for TECH-01, reusing catalogue/documentation ports."""

from typing import Any
from uuid import UUID

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.documentation import MetadataField
from kipartmanager.domain.entities import Asset, Collection, DomainError, Package, Part
from kipartmanager.ports.catalogue import CatalogueRepository
from kipartmanager.ports.documentation import DocumentationRepository


class CatalogueReader:
    def __init__(
        self,
        catalogue: Catalogue,
        repository: CatalogueRepository,
        documentation: DocumentationRepository,
    ) -> None:
        self.catalogue = catalogue
        self.repository = repository
        self.documentation = documentation

    def libraries(self) -> list[dict[str, Any]]:
        return [
            {"id": str(c.id), "name": c.name, "count": len(c.part_ids)}
            for c in self.catalogue.list_entities(Collection)
        ]

    def summary(self, part: Part, collections: list[Collection]) -> dict[str, Any]:
        profile = self.documentation.identification(part.id)
        package = self.catalogue.require(Package, part.package_id) if part.package_id else None
        return {
            "id": str(part.id),
            "reference": part.name,
            "mpn": profile.value(MetadataField.MPN),
            "manufacturer": profile.value(MetadataField.MANUFACTURER),
            "description": part.description,
            "category": profile.value(MetadataField.CATEGORY),
            "package": {"id": str(package.id), "name": package.name} if package else None,
            "libraries": [
                {"id": str(c.id), "name": c.name} for c in collections if part.id in c.part_ids
            ],
            "state": part.state.value,
        }

    def components(self, params: dict[str, Any]) -> dict[str, Any]:
        collections = self.catalogue.list_entities(Collection)
        library = params.get("library", "all")
        if library != "all" and library not in {str(c.id) for c in collections}:
            raise DomainError("Bibliothèque introuvable.")
        rows = [self.summary(p, collections) for p in self.catalogue.list_entities(Part)]
        facets = {
            "categories": sorted({r["category"] for r in rows if r["category"]}),
            "packages": sorted({r["package"]["name"] for r in rows if r["package"]}),
        }
        search = params.get("search", "").strip().casefold()
        filtered = [
            r
            for r in rows
            if (
                (library == "all" or any(c["id"] == library for c in r["libraries"]))
                and (not params.get("category") or r["category"] == params["category"])
                and (not params.get("state") or r["state"] == params["state"])
                and (
                    not params.get("package")
                    or (r["package"] and r["package"]["name"] == params["package"])
                )
                and search
                in " ".join(
                    [
                        r["reference"],
                        r["mpn"],
                        r["manufacturer"],
                        r["description"],
                        r["category"],
                        r["package"]["name"] if r["package"] else "",
                    ]
                ).casefold()
            )
        ]
        offset, limit = params.get("offset", 0), params.get("limit", 50)
        return {
            "components": filtered[offset : offset + limit],
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "facets": facets,
        }

    def component(self, identity: UUID) -> dict[str, Any]:
        part = self.catalogue.require(Part, identity)
        result = self.summary(part, self.catalogue.list_entities(Collection))
        owners: list[Part | Package] = [part]
        if part.package_id:
            owners.append(self.catalogue.require(Package, part.package_id))
        assets, selections = [], []
        for owner in owners:
            choices = self.repository.choices(owner)
            for identity in owner.asset_ids:
                asset = self.catalogue.require(Asset, identity)
                assets.append(
                    {
                        "id": str(asset.id),
                        "name": asset.name,
                        "type": asset.asset_type.value,
                        "origin": asset.origin.value,
                        "source": asset.source,
                        "owner": type(owner).__name__,
                        "validation_state": asset.validation_state,
                        "selected": any(c.asset_id == asset.id for c in choices),
                        "file": {
                            "sha256": asset.file.sha256,
                            "name": asset.file.original_name,
                            "size_bytes": asset.file.size_bytes,
                        }
                        if asset.file
                        else None,
                    }
                )
            for choice in choices:
                ref = choice.reference
                selections.append(
                    {
                        "type": choice.asset_type.value,
                        "owner": type(owner).__name__,
                        "asset_id": str(choice.asset_id) if choice.asset_id else None,
                        "external": {
                            "name": ref.name,
                            "library": ref.library,
                            "relative_path": ref.relative_path,
                            "sha256": ref.sha256,
                            "origin": ref.origin.value,
                        }
                        if ref
                        else None,
                    }
                )
        result.update(
            {
                "associated_assets": assets,
                "selections": selections,
                "documents": [
                    {
                        "id": str(d.id),
                        "asset_id": str(d.asset_id),
                        "title": d.title,
                        "revision": d.revision,
                        "language": d.language,
                        "date": d.document_date,
                        "kind": d.kind.value,
                    }
                    for d in self.documentation.documents(part.id)
                ],
                "qualification": None,
                "preview_available": False,
            }
        )
        return result
