"""Transactional SQLAlchemy adapter for the M1 catalogue port."""

import json
from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, Table, delete, insert, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    ConflictError,
    DomainError,
    Entity,
    Inventory,
    Location,
    Package,
    Part,
    PartState,
    StockItem,
)
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.domain.resolution import ResourceChoice, allowed_roles
from kipartmanager.infrastructure.asset_provenance import decode_provenance, encode_provenance
from kipartmanager.infrastructure.models import (
    AssetFileRow,
    AssetRow,
    Base,
    ChoiceRow,
    CollectionRow,
    InventoryRow,
    LocationRow,
    PackageRow,
    PartRow,
    StockRow,
    collection_parts,
    package_assets,
    part_assets,
)

ROWS: dict[type[object], type[Base]] = {
    Part: PartRow,
    Package: PackageRow,
    Asset: AssetRow,
    Inventory: InventoryRow,
    Location: LocationRow,
    Collection: CollectionRow,
    StockItem: StockRow,
}


class SqliteCatalogue:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_entities[T: Entity](self, kind: type[T]) -> list[T]:
        with Session(self.engine) as session:
            entities = [
                cast(T, self._entity(session, row)) for row in session.scalars(select(ROWS[kind]))
            ]
            return sorted(
                entities, key=lambda entity: (getattr(entity, "name", ""), str(entity.id))
            )

    def get[T: Entity](self, kind: type[T], identity: UUID) -> T | None:
        with Session(self.engine) as session:
            row = session.get(ROWS[kind], identity)
            return cast(T, self._entity(session, row)) if row is not None else None

    def save(self, entity: Entity) -> None:
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(text("BEGIN IMMEDIATE"))
                self._save(session, entity)
        except IntegrityError as error:
            raise ConflictError(
                "Conflit de nom, de stock ou de référence ; modification annulée."
            ) from error
        except SQLAlchemyError as error:
            raise DomainError("Enregistrement impossible ; modification annulée.") from error

    def seed_defaults(self, entities: tuple[Inventory | Collection, ...]) -> None:
        try:
            with Session(self.engine) as session, session.begin():
                for entity in entities:
                    if session.get(ROWS[type(entity)], entity.id) is None:
                        self._save(session, entity)
        except IntegrityError as error:
            raise ConflictError(
                "Impossible d'initialiser les inventaires et collections par défaut."
            ) from error

    @staticmethod
    def _ids(
        session: Session, table: Table, owner: str, target: str, identity: UUID
    ) -> tuple[UUID, ...]:
        return tuple(
            session.scalars(
                select(table.c[target]).where(table.c[owner] == identity).order_by(table.c[target])
            )
        )

    def _entity(self, session: Session, row: Base) -> Entity:
        if isinstance(row, PartRow):
            return Part(
                id=row.id,
                name=row.name,
                description=row.description,
                state=PartState(row.state),
                package_id=row.package_id,
                asset_ids=self._ids(session, part_assets, "part_id", "asset_id", row.id),
            )
        if isinstance(row, PackageRow):
            return Package(
                id=row.id,
                name=row.name,
                description=row.description,
                asset_ids=self._ids(session, package_assets, "package_id", "asset_id", row.id),
            )
        if isinstance(row, AssetRow):
            file_row = session.get(AssetFileRow, row.id)
            return Asset(
                id=row.id,
                name=row.name,
                asset_type=AssetType(row.asset_type),
                origin=AssetOrigin(row.origin),
                source=row.source,
                provenance=decode_provenance(row.provenance_json),
                file=AssetFile(
                    file_row.sha256,
                    file_row.size_bytes,
                    file_row.extension,
                    file_row.original_name,
                    file_row.symbol_name,
                )
                if file_row is not None
                else None,
            )
        if isinstance(row, CollectionRow):
            return Collection(
                id=row.id,
                name=row.name,
                part_ids=self._ids(session, collection_parts, "collection_id", "part_id", row.id),
            )
        if isinstance(row, InventoryRow):
            return Inventory(id=row.id, name=row.name)
        if isinstance(row, LocationRow):
            return Location(id=row.id, name=row.name)
        if isinstance(row, StockRow):
            return StockItem(
                id=row.id,
                part_id=row.part_id,
                inventory_id=row.inventory_id,
                location_id=row.location_id,
                quantity=row.quantity,
            )
        raise TypeError(f"Unsupported row: {type(row)}")

    @staticmethod
    def _save(session: Session, entity: Entity) -> None:
        row: Base
        links: tuple[Table, str, str, tuple[UUID, ...]] | None = None
        if isinstance(entity, (Part, Package)):
            for selected in session.scalars(
                select(ChoiceRow).where(ChoiceRow.owner_key == SqliteCatalogue._owner_key(entity))
            ):
                if selected.asset_id is not None and selected.asset_id not in entity.asset_ids:
                    raise ConflictError("Un asset sélectionné doit rester associé.")
        if isinstance(entity, Part):
            row = PartRow(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                state=entity.state.value,
                package_id=entity.package_id,
            )
            links = (part_assets, "part_id", "asset_id", entity.asset_ids)
        elif isinstance(entity, Package):
            row = PackageRow(id=entity.id, name=entity.name, description=entity.description)
            links = (package_assets, "package_id", "asset_id", entity.asset_ids)
        elif isinstance(entity, Asset):
            existing_asset = session.get(AssetRow, entity.id)
            if existing_asset is not None and existing_asset.provenance_json is not None:
                if (
                    decode_provenance(existing_asset.provenance_json) != entity.provenance
                    or existing_asset.source != entity.source
                    or existing_asset.origin != entity.origin.value
                ):
                    raise ConflictError("Provenance d’import immuable ; créer un nouvel asset.")
            for selected in session.scalars(
                select(ChoiceRow).where(ChoiceRow.asset_id == entity.id)
            ):
                if selected.asset_type != entity.asset_type.value:
                    raise ConflictError("Le type d'un asset sélectionné ne peut pas changer.")
            existing_file = session.get(AssetFileRow, entity.id)
            if existing_file is not None:
                existing = AssetFile(
                    existing_file.sha256,
                    existing_file.size_bytes,
                    existing_file.extension,
                    existing_file.original_name,
                    existing_file.symbol_name,
                )
                if existing != entity.file:
                    raise ConflictError("Le fichier associé ne peut pas être remplacé ni détaché.")
            row = AssetRow(
                id=entity.id,
                name=entity.name,
                asset_type=entity.asset_type.value,
                origin=entity.origin.value,
                source=entity.source,
                provenance_json=encode_provenance(entity.provenance),
                validation_state=entity.validation_state,
            )
        elif isinstance(entity, Collection):
            row = CollectionRow(id=entity.id, name=entity.name)
            links = (collection_parts, "collection_id", "part_id", entity.part_ids)
        elif isinstance(entity, Inventory):
            row = InventoryRow(id=entity.id, name=entity.name)
        elif isinstance(entity, Location):
            row = LocationRow(id=entity.id, name=entity.name)
        else:
            row = StockRow(
                id=entity.id,
                part_id=entity.part_id,
                inventory_id=entity.inventory_id,
                location_id=entity.location_id,
                quantity=entity.quantity,
            )
        session.merge(row)
        session.flush()
        if isinstance(entity, Asset) and entity.file is not None and existing_file is None:
            session.add(
                AssetFileRow(
                    asset_id=entity.id,
                    sha256=entity.file.sha256,
                    size_bytes=entity.file.size_bytes,
                    extension=entity.file.extension,
                    original_name=entity.file.original_name,
                    symbol_name=entity.file.symbol_name,
                )
            )
        if links is not None:
            table, owner, target, identities = links
            session.execute(delete(table).where(table.c[owner] == entity.id))
            if identities:
                session.execute(
                    insert(table), [{owner: entity.id, target: identity} for identity in identities]
                )

    @staticmethod
    def _owner_key(owner: Part | Package) -> str:
        return f"{type(owner).__name__}:{owner.id.hex}"

    @staticmethod
    def _choice(row: ChoiceRow) -> ResourceChoice:
        reference = None
        if row.reference_json:
            try:
                data = json.loads(row.reference_json)
                data["asset_type"] = AssetType(data["asset_type"])
                reference = KiCadReference(**data)
            except (ValueError, TypeError, KeyError) as error:
                raise DomainError("Référence sélectionnée illisible ; choix conservé.") from error
        return ResourceChoice(AssetType(row.asset_type), row.asset_id, reference)

    def choices(self, owner: Part | Package) -> tuple[ResourceChoice, ...]:
        with Session(self.engine) as session:
            return tuple(
                self._choice(row)
                for row in session.scalars(
                    select(ChoiceRow)
                    .where(ChoiceRow.owner_key == self._owner_key(owner))
                    .order_by(ChoiceRow.asset_type)
                )
            )

    def choose(
        self, owner: Part | Package, choice: ResourceChoice, expected: ResourceChoice | None
    ) -> None:
        try:
            with Session(self.engine) as session, session.begin():
                # Serialize SQLite writers before reading the expected choice.
                session.execute(text("BEGIN IMMEDIATE"))
                owner_row = session.get(ROWS[type(owner)], owner.id)
                if owner_row is None:
                    raise DomainError("Propriétaire introuvable.")
                if choice.asset_type not in allowed_roles(owner):
                    raise DomainError("Rôle incompatible avec le propriétaire.")
                key = self._owner_key(owner)
                previous = session.get(ChoiceRow, (key, choice.asset_type.value))
                if (self._choice(previous) if previous else None) != expected:
                    raise ConflictError("La sélection a changé ; modification annulée.")
                if choice.asset_id is not None:
                    asset_row = session.get(AssetRow, choice.asset_id)
                    if (
                        asset_row is None
                        or asset_row.asset_type != choice.asset_type.value
                        or session.get(AssetFileRow, choice.asset_id) is None
                    ):
                        raise DomainError("Asset absent, sans fichier ou de type incompatible.")
                    table, column = (
                        (part_assets, "part_id")
                        if isinstance(owner, Part)
                        else (package_assets, "package_id")
                    )
                    if (
                        session.scalar(
                            select(table.c.asset_id).where(
                                table.c[column] == owner.id, table.c.asset_id == choice.asset_id
                            )
                        )
                        is None
                    ):
                        session.execute(
                            insert(table), {column: owner.id, "asset_id": choice.asset_id}
                        )
                session.merge(
                    ChoiceRow(
                        owner_key=key,
                        asset_type=choice.asset_type.value,
                        part_id=owner.id if isinstance(owner, Part) else None,
                        package_id=owner.id if isinstance(owner, Package) else None,
                        asset_id=choice.asset_id,
                        reference_json=json.dumps(
                            asdict(choice.reference), sort_keys=True, ensure_ascii=False
                        )
                        if choice.reference
                        else "",
                    )
                )
        except IntegrityError as error:
            raise ConflictError("Conflit de sélection ; modification annulée.") from error
        except SQLAlchemyError as error:
            raise DomainError("Sélection impossible ; modification annulée.") from error
