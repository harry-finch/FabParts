"""Atomic identification acceptance and additive PDF associations."""

from typing import Protocol
from uuid import UUID

from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.documentation import Identification, MetadataProposal, PartDocument
from kipartmanager.domain.entities import Asset


class DocumentationRepository(Protocol):
    def identification(self, part_id: UUID) -> Identification: ...
    def save_identification(self, value: Identification, expected: Identification) -> None: ...
    def documents(self, part_id: UUID) -> tuple[PartDocument, ...]: ...
    def add_document(self, document: PartDocument, asset: Asset, *, new_asset: bool) -> None: ...


class ProposalReader(Protocol):
    def read(self, source: str) -> "MetadataProposal": ...


class DatasheetSettings(Protocol):
    def load(self) -> "DatasheetConfiguration": ...
    def save(self, config: "DatasheetConfiguration") -> None: ...


class DatasheetProvider(Protocol):
    def download(self, url: str, config: "DatasheetConfiguration") -> "DatasheetDownload": ...
