"""Traceable local enrichment and optional manufacturer PDF retrieval."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.documentation import (
    DocumentDetails,
    Identification,
    MetadataField,
    MetadataProposal,
    PartDocument,
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.ports.documentation import (
    DatasheetProvider,
    DatasheetSettings,
    DocumentationRepository,
    ProposalReader,
)


class Documentation:
    def __init__(
        self,
        catalogue: Catalogue,
        repository: DocumentationRepository,
        reader: ProposalReader,
        settings: DatasheetSettings,
        provider: DatasheetProvider | None = None,
    ) -> None:
        self.catalogue, self.repository, self.reader = catalogue, repository, reader
        self.settings, self.provider = settings, provider

    def identification(self, part_id: UUID) -> Identification:
        self.catalogue.require(Part, part_id)
        return self.repository.identification(part_id)

    def read_proposal(self, source: str) -> MetadataProposal:
        return self.reader.read(source)

    def accept(
        self,
        expected: Identification,
        proposal: MetadataProposal,
        fields: tuple[MetadataField, ...],
        *,
        replace_existing: bool = False,
    ) -> Identification:
        self.catalogue.require(Part, expected.part_id)
        updated = expected.accept(
            proposal,
            fields,
            replace_existing=replace_existing,
            recorded_at=datetime.now(UTC).isoformat(),
        )
        self.repository.save_identification(updated, expected)
        return updated

    def documents(self, part_id: UUID) -> tuple[PartDocument, ...]:
        self.catalogue.require(Part, part_id)
        return self.repository.documents(part_id)

    def require_pdf(self, asset: Asset) -> None:
        if (
            asset.asset_type is not AssetType.DATASHEET
            or asset.file is None
            or self.catalogue.store is None
        ):
            raise DomainError("Un PDF géré disponible dans l’Asset Store est requis.")
        self.catalogue.store.verify(asset.file)

    def add_existing(self, part_id: UUID, asset_id: UUID, details: DocumentDetails) -> PartDocument:
        self.catalogue.require(Part, part_id)
        asset = self.catalogue.require(Asset, asset_id)
        self.require_pdf(asset)
        record = details.record(part_id, asset_id, datetime.now(UTC).isoformat())
        self.repository.add_document(record, asset, new_asset=False)
        return record

    def import_local(self, part_id: UUID, source: str, details: DocumentDetails) -> PartDocument:
        self.catalogue.require(Part, part_id)
        if self.catalogue.store is None:
            raise DomainError("Asset Store indisponible.")
        identity = uuid4()
        record = details.record(part_id, identity, datetime.now(UTC).isoformat())
        file = self.catalogue.store.import_file(source)
        asset = Asset(
            id=identity,
            name=details.title,
            asset_type=AssetType.DATASHEET,
            origin=details.source.origin,
            source=details.source.reference,
            file=file,
        )
        self.require_pdf(asset)
        self.repository.add_document(record, asset, new_asset=True)
        return record

    def configuration(self) -> DatasheetConfiguration:
        return self.settings.load()

    def configure(self, config: DatasheetConfiguration) -> None:
        self.settings.save(config)

    def download(self, url: str) -> DatasheetDownload:
        config = self.configuration()
        config.authorize(url)
        if self.provider is None:
            raise DomainError("Adaptateur constructeur absent ; documents locaux conservés.")
        return self.provider.download(url, config)

    def import_download(
        self, part_id: UUID, download: DatasheetDownload, details: DocumentDetails
    ) -> PartDocument:
        self.catalogue.require(Part, part_id)
        self.configuration().authorize(download.url)
        if (
            details.source.origin is not AssetOrigin.MANUFACTURER
            or details.source.reference != download.url
        ):
            raise DomainError("La provenance constructeur doit correspondre à l’URL téléchargée.")
        if self.catalogue.store is None:
            raise DomainError("Asset Store indisponible.")
        identity = uuid4()
        record = details.record(part_id, identity, datetime.now(UTC).isoformat())
        file = self.catalogue.store.import_content(download.content, download.filename)
        if file.sha256 != download.sha256:
            raise DomainError("Empreinte du téléchargement incohérente ; document non enregistré.")
        asset = Asset(
            id=identity,
            name=details.title,
            asset_type=AssetType.DATASHEET,
            origin=AssetOrigin.MANUFACTURER,
            source=download.url,
            file=file,
        )
        self.require_pdf(asset)
        self.repository.add_document(record, asset, new_asset=True)
        return record

    def retrieve(self, part_id: UUID, document_id: UUID, destination: str) -> None:
        record = next((d for d in self.documents(part_id) if d.id == document_id), None)
        if record is None:
            raise DomainError("Document introuvable pour ce composant.")
        asset = self.catalogue.require(Asset, record.asset_id)
        self.require_pdf(asset)
        assert asset.file is not None and self.catalogue.store is not None
        self.catalogue.store.retrieve(asset.file, destination)
