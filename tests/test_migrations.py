"""Fresh Alembic schema, constraints and disposable downgrade."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError

from kipartmanager.domain.entities import Asset, Collection, Part
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.models import AssetFileRow, Base, StockRow


def test_migration_matches_orm_and_repeated_upgrade(engine: Engine) -> None:
    migrate(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0007_asset_provenance"
        )
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


@pytest.mark.parametrize("quantity", [-1, 0.5])
def test_database_rejects_invalid_stock(engine: Engine, quantity: int) -> None:
    # Populate valid parents so the quantity check, rather than a FK, rejects the row.
    part_id, inventory_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO parts(id,name,description,state) VALUES (:id,'Timer','','DRAFT')"),
            {"id": part_id.hex},
        )
        connection.execute(
            text("INSERT INTO inventories(id,name) VALUES (:id,'Test')"), {"id": inventory_id.hex}
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(StockRow).values(
                id=uuid4(), part_id=part_id, inventory_id=inventory_id, quantity=quantity
            )
        )


def test_database_rejects_missing_reference(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(StockRow).values(id=uuid4(), part_id=uuid4(), inventory_id=uuid4(), quantity=0)
        )


def test_disposable_downgrade_then_upgrade(engine: Engine) -> None:
    migrate(engine, "base", downgrade=True)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    migrate(engine)
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())


def test_upgrade_m1_preserves_data_and_associations(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "previous.sqlite3")
    part_id, asset_id, collection_id = uuid4(), uuid4(), uuid4()
    try:
        migrate(engine, "0001_catalogue")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO parts(id,name,description,state) "
                    "VALUES (:id,'Timer','retained','IDENTIFIED')"
                ),
                {"id": part_id.hex},
            )
            connection.execute(
                text(
                    "INSERT INTO assets(id,name,asset_type,origin,source,validation_state) "
                    "VALUES (:id,'Datasheet','DATASHEET','USER_PROVIDED',"
                    "'original source','UNCHECKED')"
                ),
                {"id": asset_id.hex},
            )
            connection.execute(
                text("INSERT INTO collections(id,name) VALUES (:id,'Previous')"),
                {"id": collection_id.hex},
            )
            connection.execute(
                text("INSERT INTO part_assets(part_id,asset_id) VALUES (:part,:asset)"),
                {"part": part_id.hex, "asset": asset_id.hex},
            )
            connection.execute(
                text(
                    "INSERT INTO collection_parts(collection_id,part_id) VALUES (:collection,:part)"
                ),
                {"collection": collection_id.hex, "part": part_id.hex},
            )
        migrate(engine)
        repository = SqliteCatalogue(engine)
        asset = repository.get(Asset, asset_id)
        part = repository.get(Part, part_id)
        collection = repository.get(Collection, collection_id)
        assert asset is not None and asset.file is None and asset.source == "original source"
        assert part is not None and part.asset_ids == (asset_id,) and part.description == "retained"
        assert collection is not None and collection.part_ids == (part_id,)
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "hash_value,size,extension,name",
    [
        ("invalid", 4, ".pdf", "ok.pdf"),
        ("a" * 64, 0, ".pdf", "ok.pdf"),
        ("a" * 64, 4, ".txt", "ok.txt"),
        ("a" * 64, 4, ".pdf", "../bad.pdf"),
    ],
)
def test_file_identity_constraints(
    engine: Engine, hash_value: str, size: int, extension: str, name: str
) -> None:
    asset_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets(id,name,asset_type,origin,source,validation_state) "
                "VALUES (:id,'PDF','DATASHEET','USER_PROVIDED','','UNCHECKED')"
            ),
            {"id": asset_id.hex},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(AssetFileRow).values(
                asset_id=asset_id,
                sha256=hash_value,
                size_bytes=size,
                extension=extension,
                original_name=name,
            )
        )


def test_m8_upgrade_keeps_previous_file_identity(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "m7.sqlite3")
    identity = uuid4()
    try:
        migrate(engine, "0004_validation_reports")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets(id,name,asset_type,origin,source,validation_state) "
                    "VALUES (:id,'R','SYMBOL','USER_PROVIDED','retained','UNCHECKED')"
                ),
                {"id": identity.hex},
            )
            connection.execute(
                text(
                    "INSERT INTO asset_files(asset_id,sha256,size_bytes,extension,original_name) "
                    "VALUES (:id,:hash,10,'.kicad_sym','R.kicad_sym')"
                ),
                {"id": identity.hex, "hash": "a" * 64},
            )
        migrate(engine)
        asset = SqliteCatalogue(engine).get(Asset, identity)
        assert asset is not None and asset.file is not None
        assert asset.source == "retained" and asset.file.sha256 == "a" * 64
        assert asset.file.symbol_name == ""
        migrate(engine, "0004_validation_reports", downgrade=True)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT sha256 FROM asset_files")) == "a" * 64
    finally:
        engine.dispose()


def test_m8_downgrade_refuses_loss_of_symbol_selection(engine: Engine) -> None:
    from kipartmanager.domain.asset_files import AssetFile
    from kipartmanager.domain.entities import AssetOrigin, AssetType

    asset = Asset(
        name="Derived",
        asset_type=AssetType.SYMBOL,
        origin=AssetOrigin.KICAD_OFFICIAL,
        file=AssetFile("a" * 64, 10, ".kicad_sym", "Device.kicad_sym", "Derived"),
    )
    SqliteCatalogue(engine).save(asset)
    with pytest.raises(RuntimeError, match="would be lost"):
        migrate(engine, "0004_validation_reports", downgrade=True)
    assert SqliteCatalogue(engine).get(Asset, asset.id) == asset
