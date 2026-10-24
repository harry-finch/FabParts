"""Managed-file identity survives database reopening and source removal."""

from pathlib import Path

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate


def test_file_persists_without_source(tmp_path: Path) -> None:
    database = tmp_path / "database" / "catalogue.sqlite3"
    store = LocalAssetStore(tmp_path / "assets")
    engine = create_database_engine(database)
    migrate(engine)
    catalogue = Catalogue(SqliteCatalogue(engine), store)
    imports = AssetImports(catalogue, store)
    source = tmp_path / "user.pdf"
    source.write_bytes(b"original managed data")
    asset = imports.import_file(str(source))
    engine.dispose()
    source.unlink()
    engine = create_database_engine(database)
    try:
        migrate(engine)
        reopened_store = LocalAssetStore(tmp_path / "assets")
        catalogue = Catalogue(SqliteCatalogue(engine), reopened_store)
        assert catalogue.require(Asset, asset.id) == asset
        destination = tmp_path / "restored.pdf"
        AssetImports(catalogue, reopened_store).retrieve(asset.id, str(destination))
        assert destination.read_bytes() == b"original managed data"
    finally:
        engine.dispose()
