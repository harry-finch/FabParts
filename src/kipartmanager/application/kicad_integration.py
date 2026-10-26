"""Install only committed, verified historical publications, never current catalogue data."""

from typing import Any
from uuid import UUID

from kipartmanager.application.publications import Publications
from kipartmanager.domain.entities import DomainError
from kipartmanager.ports.kicad_integration import IntegrationStore


class KiCadIntegration:
    def __init__(self, publications: Publications, store: IntegrationStore) -> None:
        self.publications, self.store = publications, store

    def get(self, identity: str, target: str = "") -> dict[str, Any]:
        return self.store.status(UUID(identity), target)

    def prepare(self, identity: str, target: str, version: int) -> dict[str, Any]:
        publication = next(
            (
                p
                for p in self.publications.list_publications(UUID(identity))
                if p.version == version
            ),
            None,
        )
        if publication is None:
            raise DomainError("PUBLICATION_REQUIRED: committed version required")
        self.publications.verify(publication)
        return self.store.prepare(publication, target)

    def activate(self, identity: str, target: str, handle: str) -> dict[str, Any]:
        return self.store.activate(UUID(identity), target, handle)

    def verify(self, identity: str, target: str) -> dict[str, Any]:
        return self.store.verify(UUID(identity), target)

    def recovery(self, identity: str, target: str) -> dict[str, Any]:
        return self.store.recovery(UUID(identity), target)

    def recover(self, identity: str, target: str, handle: str) -> dict[str, Any]:
        return self.store.recover(UUID(identity), target, handle)
