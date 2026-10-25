"""One transaction for catalogue, identification and a durable confirmation receipt."""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from kipartmanager.ports.catalogue import CatalogueRepository
from kipartmanager.ports.documentation import DocumentationRepository
from kipartmanager.ports.resolution import ResolutionRepository


class IngestionCatalogue(CatalogueRepository, ResolutionRepository, Protocol):
    pass


@dataclass(frozen=True)
class Receipt:
    operation_id: UUID
    request_sha256: str
    part_id: UUID


class IngestionTransaction(Protocol):
    @property
    def catalogue(self) -> IngestionCatalogue: ...
    @property
    def documentation(self) -> DocumentationRepository: ...
    def receipt(self, operation_id: UUID) -> Receipt | None: ...
    def record(self, receipt: Receipt) -> None: ...


class IngestionTransactions(Protocol):
    def begin(self) -> AbstractContextManager[IngestionTransaction]: ...
    def receipt(self, operation_id: UUID) -> Receipt | None: ...
