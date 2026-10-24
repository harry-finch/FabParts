"""Persistence, shared associations and application invariants."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from kipartmanager.application.catalogue import Catalogue
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
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate


def test_roundtrip_all_entities_and_reopen(
    catalogue: Catalogue, tmp_path: Path, engine: Engine
) -> None:
    symbol = Asset(
        name="NE555",
        asset_type=AssetType.SYMBOL,
        origin=AssetOrigin.USER_PROVIDED,
        source="user reference",
    )
    footprint = Asset(
        name="DIP8",
        asset_type=AssetType.FOOTPRINT,
        origin=AssetOrigin.KICAD_OFFICIAL,
        source="Package_DIP:DIP-8",
    )
    for asset in (symbol, footprint):
        catalogue.save(asset)
    package = Package(name="DIP8", asset_ids=(footprint.id,))
    catalogue.save(package)
    parts = [
        Part(name=name, package_id=package.id, asset_ids=(symbol.id,))
        for name in ("NE555P", "NE556P")
    ]
    for part in parts:
        catalogue.save(part)
    inventory = catalogue.list_entities(Inventory)[0]
    location = Location(name="Tiroir A")
    catalogue.save(location)
    stock = StockItem(
        part_id=parts[0].id, inventory_id=inventory.id, location_id=location.id, quantity=4
    )
    collection = Collection(name="TestParts", part_ids=(parts[0].id,))
    catalogue.save(stock)
    catalogue.save(collection)
    changes: list[Entity] = [
        replace(symbol, source="updated reference"),
        replace(package, description="8 pins"),
        replace(parts[0], description="timer").transition(PartState.IDENTIFIED),
        replace(inventory, name="Workshop"),
        replace(location, name="Tiroir B"),
        replace(stock, quantity=0),
        replace(collection, name="Timers"),
    ]
    for entity in changes:
        catalogue.save(entity)
    engine.dispose()
    reopened = create_database_engine(tmp_path / "database" / "catalogue.sqlite3")
    try:
        migrate(reopened)
        service = Catalogue(SqliteCatalogue(reopened))
        service.initialize_defaults()
        for entity in changes:
            assert service.require(type(entity), entity.id) == entity
        assert service.require(Part, parts[1].id).package_id == package.id
        assert service.require(Collection, collection.id).part_ids == (parts[0].id,)
        assert service.require(Part, parts[0].id).state == PartState.IDENTIFIED
        assert len(service.list_entities(Inventory)) == 2
    finally:
        reopened.dispose()


def test_defaults_repeatable_and_preserve_edits(catalogue: Catalogue) -> None:
    original = catalogue.list_entities(Inventory)
    catalogue.save(replace(original[0], name="Renamed"))
    for _ in range(3):
        catalogue.initialize_defaults()
    assert {item.id for item in catalogue.list_entities(Inventory)} == {
        item.id for item in original
    }
    assert catalogue.require(Inventory, original[0].id).name == "Renamed"
    assert {item.name for item in catalogue.list_entities(Collection)} == {
        "LabParts",
        "PersonalParts",
    }


def test_invalid_references_and_asset_roles(catalogue: Catalogue) -> None:
    with pytest.raises(DomainError):
        catalogue.save(Part(name="Missing", package_id=uuid4()))
    symbol = Asset(name="symbol", asset_type=AssetType.SYMBOL, origin=AssetOrigin.USER_PROVIDED)
    catalogue.save(symbol)
    with pytest.raises(DomainError):
        catalogue.save(Package(name="Wrong role", asset_ids=(symbol.id,)))
    part = Part(name="Timer", asset_ids=(symbol.id,))
    catalogue.save(part)
    with pytest.raises(DomainError):
        catalogue.save(replace(symbol, asset_type=AssetType.FOOTPRINT))
    with pytest.raises(DomainError):
        catalogue.save(replace(part, asset_ids=(symbol.id, symbol.id)))
    with pytest.raises(DomainError):
        catalogue.save(Collection(name="Missing", part_ids=(uuid4(),)))
    assert catalogue.require(Asset, symbol.id) == symbol


def test_stock_unique_and_zero_does_not_change_catalogue(catalogue: Catalogue) -> None:
    part = Part(name="Timer")
    catalogue.save(part)
    inventories = catalogue.list_entities(Inventory)
    stock = StockItem(part_id=part.id, inventory_id=inventories[0].id, quantity=0)
    catalogue.save(stock)
    with pytest.raises(ConflictError):
        catalogue.save(replace(stock, id=uuid4(), quantity=9))
    catalogue.save(StockItem(part_id=part.id, inventory_id=inventories[1].id, quantity=2))
    collection = Collection(name="Zero stock", part_ids=(part.id,))
    catalogue.save(collection)
    assert catalogue.require(Part, part.id) == part
    assert catalogue.require(Collection, collection.id) == collection
    assert catalogue.require(StockItem, stock.id).quantity == 0


def test_state_changes_cannot_bypass_domain(catalogue: Catalogue) -> None:
    part = Part(name="Timer")
    with pytest.raises(DomainError):
        catalogue.save(replace(part, state=PartState.IDENTIFIED))
    catalogue.save(part)
    catalogue.save(part.transition(PartState.IDENTIFIED))
    with pytest.raises(DomainError):
        catalogue.save(part)


def test_duplicate_link_rolls_back_entire_edit(catalogue: Catalogue) -> None:
    asset = Asset(name="symbol", asset_type=AssetType.SYMBOL, origin=AssetOrigin.USER_PROVIDED)
    catalogue.save(asset)
    part = Part(name="Original", asset_ids=(asset.id,))
    catalogue.save(part)
    with pytest.raises(ConflictError):
        catalogue.repository.save(replace(part, name="Changed", asset_ids=(asset.id, asset.id)))
    assert catalogue.require(Part, part.id) == part


def test_unique_names_report_conflict(catalogue: Catalogue) -> None:
    with pytest.raises(ConflictError):
        catalogue.save(Inventory(name="Lab"))


def test_unordered_memberships_roundtrip(catalogue: Catalogue) -> None:
    parts = [Part(name=name) for name in ("First", "Second")]
    for part in parts:
        catalogue.save(part)
    collection = Collection(name="Both", part_ids=(parts[1].id, parts[0].id))
    catalogue.save(collection)
    assert catalogue.require(Collection, collection.id) == collection
