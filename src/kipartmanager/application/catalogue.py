"""M1 use cases and association checks."""

from uuid import NAMESPACE_URL, UUID, uuid5

from kipartmanager.domain.entities import (
    Asset,
    Collection,
    DomainError,
    Entity,
    Inventory,
    Location,
    Package,
    Part,
    StockItem,
    require_distinct,
    validate_asset_associations,
)
from kipartmanager.ports.asset_store import AssetStore
from kipartmanager.ports.catalogue import CatalogueRepository


class Catalogue:
    def __init__(self, repository: CatalogueRepository, store: AssetStore | None = None) -> None:
        self.repository = repository
        self.store = store

    def initialize_defaults(self) -> None:
        defaults: list[Inventory | Collection] = []
        for kind, names in (
            (Inventory, ("Lab", "Personal")),
            (Collection, ("LabParts", "PersonalParts")),
        ):
            for name in names:
                identity = uuid5(NAMESPACE_URL, f"urn:kipartmanager:{kind.__name__}:{name}")
                defaults.append(kind(id=identity, name=name))
        self.repository.seed_defaults(tuple(defaults))

    def list_entities[T: Entity](self, kind: type[T]) -> list[T]:
        return self.repository.list_entities(kind)

    def require[T: Entity](self, kind: type[T], identity: UUID) -> T:
        entity = self.repository.get(kind, identity)
        if entity is None:
            raise DomainError(f"{kind.__name__} introuvable : {identity}.")
        return entity

    def save(self, entity: Entity) -> None:
        if isinstance(entity, Part):
            previous = self.repository.get(Part, entity.id)
            if previous is not None and previous.state != entity.state:
                previous.transition(entity.state)
            if previous is None and entity.state.value != "DRAFT":
                raise DomainError("Un nouveau composant commence en DRAFT.")
            if entity.package_id is not None:
                self.require(Package, entity.package_id)
            self._assets(entity)
        elif isinstance(entity, Package):
            self._assets(entity)
        elif isinstance(entity, Collection):
            require_distinct(entity.part_ids)
            for identity in entity.part_ids:
                self.require(Part, identity)
        elif isinstance(entity, StockItem):
            self.require(Part, entity.part_id)
            self.require(Inventory, entity.inventory_id)
            if entity.location_id is not None:
                self.require(Location, entity.location_id)
        elif isinstance(entity, Asset):
            previous_asset = self.repository.get(Asset, entity.id)
            if (
                previous_asset is not None
                and previous_asset.file is not None
                and entity.file != previous_asset.file
            ):
                raise DomainError("Le fichier associé ne peut pas être remplacé ni détaché.")
            if entity.file is not None:
                if self.store is None:
                    raise DomainError("L'Asset Store est requis pour enregistrer un fichier.")
                self.store.verify(entity.file)
            # A metadata type change must not invalidate existing associations.
            owners: list[Part | Package] = [*self.list_entities(Part), *self.list_entities(Package)]
            for owner in owners:
                if entity.id in owner.asset_ids:
                    assets = tuple(
                        entity if identity == entity.id else self.require(Asset, identity)
                        for identity in owner.asset_ids
                    )
                    validate_asset_associations(owner, assets)
        self.repository.save(entity)

    def _assets(self, owner: Part | Package) -> None:
        assets = tuple(self.require(Asset, identity) for identity in owner.asset_ids)
        validate_asset_associations(owner, assets)
        for choice in self.repository.choices(owner):
            if choice.asset_id is not None and choice.asset_id not in owner.asset_ids:
                raise DomainError(
                    "Un asset sélectionné doit rester associé ; changer le choix dans le resolver."
                )
