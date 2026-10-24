"""Import, attach, integrity-check and retrieve use cases."""

from dataclasses import replace
from uuid import UUID

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset, AssetOrigin, DomainError
from kipartmanager.ports.asset_store import AssetStore


class AssetImports:
    def __init__(self, catalogue: Catalogue, store: AssetStore) -> None:
        self.catalogue, self.store = catalogue, store

    def import_file(
        self,
        source: str,
        *,
        name: str = "",
        origin: AssetOrigin = AssetOrigin.USER_PROVIDED,
        source_reference: str = "",
    ) -> Asset:
        file = self.store.import_file(source)
        asset = Asset(
            name=name.strip() or file.original_name,
            asset_type=file.asset_type,
            origin=origin,
            source=source_reference or source,
            file=file,
        )
        self.catalogue.save(asset)
        return asset

    def import_content(
        self,
        content: bytes,
        filename: str,
        *,
        name: str,
        origin: AssetOrigin,
        source_reference: str,
        symbol_name: str = "",
    ) -> Asset:
        file = replace(self.store.import_content(content, filename), symbol_name=symbol_name)
        asset = Asset(
            name=name, asset_type=file.asset_type, origin=origin, source=source_reference, file=file
        )
        self.catalogue.save(asset)
        return asset

    def attach_file(self, identity: UUID, source: str) -> Asset:
        asset = self.catalogue.require(Asset, identity)
        if asset.file is not None:
            raise DomainError("Cet asset possède déjà un fichier ; importer un nouvel asset.")
        file = self.store.import_file(source)
        updated = replace(asset, file=file)
        self.catalogue.save(updated)
        return updated

    def verify(self, identity: UUID) -> None:
        asset = self.catalogue.require(Asset, identity)
        if asset.file is None:
            raise DomainError("Cet asset ne possède pas de fichier géré.")
        self.store.verify(asset.file)

    def retrieve(self, identity: UUID, destination: str) -> None:
        asset = self.catalogue.require(Asset, identity)
        if asset.file is None:
            raise DomainError("Cet asset ne possède pas de fichier géré.")
        self.store.retrieve(asset.file, destination)
