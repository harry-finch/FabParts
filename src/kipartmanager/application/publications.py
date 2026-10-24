"""Publish qualified snapshots; historical operations never query current data."""

from uuid import UUID

from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.domain.build import BuildResult
from kipartmanager.domain.entities import Collection, DomainError
from kipartmanager.domain.publication import Publication, PublicationSnapshot
from kipartmanager.ports.publications import PublicationStore


class Publications:
    def __init__(self, publisher: LocalPublisher, store: PublicationStore) -> None:
        self.publisher, self.store = publisher, store

    def publish(self, collection: Collection, version: int) -> Publication:
        plan = self.publisher.plan(collection)
        report = self.publisher.validation.require_publishable(collection)
        if report.fingerprint != plan.fingerprint:
            raise DomainError("Collection modifiée ; revalider avant publication.")

        def confirm() -> None:
            if self.publisher.plan(collection) != plan:
                raise DomainError("Collection modifiée pendant la publication ; revalider.")

        return self.store.publish(PublicationSnapshot(plan, report), version, confirm)

    def list_publications(self, collection_id: UUID | None = None) -> tuple[Publication, ...]:
        return self.store.list_publications(collection_id)

    def verify(self, publication: Publication) -> None:
        self.store.verify(publication)

    def rebuild(self, publication: Publication, destination: str) -> BuildResult:
        return self.store.rebuild(publication, destination)
