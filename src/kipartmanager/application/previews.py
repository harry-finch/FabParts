"""Inspect resources without choosing, importing or qualifying them."""

from dataclasses import dataclass

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset, AssetType, DomainError
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ports.previews import Drawing, Mesh, PreviewContent, PreviewReader, Primitive

__all__ = ["Drawing", "Mesh", "Primitive", "Preview", "Previews"]


@dataclass(frozen=True)
class Preview:
    name: str
    kind: AssetType
    origin: str
    source: str
    sha256: str
    content: PreviewContent


class Previews:
    def __init__(self, catalogue: Catalogue, reader: PreviewReader) -> None:
        self.catalogue, self.reader = catalogue, reader

    def inspect(self, choice: ResourceChoice) -> Preview:
        if choice.asset_id is not None:
            asset = self.catalogue.require(Asset, choice.asset_id)
            if asset.file is None:
                raise DomainError("Aucun fichier associé à cette ressource.")
            if asset.asset_type != choice.asset_type or asset.file.asset_type != choice.asset_type:
                raise DomainError("Le type du fichier ne correspond pas au rôle demandé.")
            return Preview(
                asset.name,
                asset.asset_type,
                asset.origin.value,
                asset.source + ("\n" + asset.provenance.summary if asset.provenance else ""),
                asset.file.sha256,
                self.reader.managed(asset.file),
            )
        assert choice.reference is not None
        ref = choice.reference
        return Preview(
            ref.name,
            ref.asset_type,
            ref.origin.value,
            ref.identifier + " · " + ref.relative_path,
            ref.sha256,
            self.reader.official(ref),
        )
