"""Storage contract for the seven M1 entities."""

from typing import Protocol
from uuid import UUID

from kipartmanager.domain.entities import Collection, Entity, Inventory, Package, Part
from kipartmanager.domain.resolution import ResourceChoice


class CatalogueRepository(Protocol):
    def list_entities[T: Entity](self, kind: type[T]) -> list[T]: ...

    def get[T: Entity](self, kind: type[T], identity: UUID) -> T | None: ...

    def save(self, entity: Entity) -> None: ...

    def seed_defaults(self, entities: tuple[Inventory | Collection, ...]) -> None: ...

    def choices(self, owner: Part | Package) -> tuple[ResourceChoice, ...]: ...
