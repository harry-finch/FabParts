"""Historical manifests, retained dependencies and exclusive reconstruction."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from kipartmanager.domain.build import BuildResult
from kipartmanager.domain.publication import Publication, PublicationSnapshot


class PublicationStore(Protocol):
    def publish(
        self, snapshot: PublicationSnapshot, version: int, confirm: Callable[[], None]
    ) -> Publication: ...

    def list_publications(self, collection_id: UUID | None = None) -> tuple[Publication, ...]: ...

    def verify(self, publication: Publication) -> None: ...

    def rebuild(self, publication: Publication, destination: str) -> BuildResult: ...
