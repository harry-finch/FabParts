"""Database/store coordination, provenance and interruption recovery."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.asset_files import AssetStoreError
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue


def services(engine: Engine, tmp_path: Path) -> tuple[Catalogue, LocalAssetStore, AssetImports]:
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(SqliteCatalogue(engine), store)
    return catalogue, store, AssetImports(catalogue, store)


def test_duplicate_content_preserves_identities_and_provenance(
    engine: Engine, tmp_path: Path
) -> None:
    catalogue, store, imports = services(engine, tmp_path)
    source = tmp_path / "datasheet.pdf"
    source.write_bytes(b"same content")
    first = imports.import_file(str(source), name="User PDF")
    second = imports.import_file(
        str(source),
        name="Manufacturer PDF",
        origin=AssetOrigin.MANUFACTURER,
        source_reference="manufacturer reference",
    )
    assert first.id != second.id
    assert first.file == second.file
    assert catalogue.require(Asset, first.id).origin == AssetOrigin.USER_PROVIDED
    assert catalogue.require(Asset, second.id).source == "manufacturer reference"
    assert len(list((store.root / "blobs").glob("*/*"))) == 1
    assert first.validation_state == second.validation_state == "UNCHECKED"
    part = Part(name="Timer", asset_ids=(first.id, second.id))
    catalogue.save(part)
    assert catalogue.require(Part, part.id) == part


def test_attach_preserves_metadata_and_prevents_replacement(engine: Engine, tmp_path: Path) -> None:
    catalogue, store, imports = services(engine, tmp_path)
    asset = Asset(
        name="Existing datasheet",
        asset_type=AssetType.DATASHEET,
        origin=AssetOrigin.USER_PROVIDED,
        source="original provenance",
    )
    catalogue.save(asset)
    part = Part(name="Timer", asset_ids=(asset.id,))
    catalogue.save(part)
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"pdf data")
    attached = imports.attach_file(asset.id, str(source))
    assert replace(attached, file=None) == asset
    assert catalogue.require(Part, part.id) == part
    with pytest.raises(DomainError):
        imports.attach_file(asset.id, str(source))
    with pytest.raises(DomainError):
        catalogue.save(replace(attached, file=None))
    with pytest.raises(DomainError):
        catalogue.repository.save(replace(attached, file=None))
    assert catalogue.require(Asset, asset.id) == attached
    assert attached.file is not None
    store.verify(attached.file)


def test_wrong_type_and_missing_managed_file(engine: Engine, tmp_path: Path) -> None:
    catalogue, store, imports = services(engine, tmp_path)
    asset = Asset(
        name="Footprint", asset_type=AssetType.FOOTPRINT, origin=AssetOrigin.USER_PROVIDED
    )
    catalogue.save(asset)
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"pdf data")
    with pytest.raises(DomainError):
        imports.attach_file(asset.id, str(source))
    assert catalogue.require(Asset, asset.id).file is None
    imported = imports.import_file(str(source))
    assert imported.file is not None
    (store.root / imported.file.relative_key).unlink()
    with pytest.raises(AssetStoreError):
        imports.verify(imported.id)
    with pytest.raises(AssetStoreError):
        imports.retrieve(imported.id, str(tmp_path / "copy.pdf"))


def test_database_failure_leaves_reusable_orphan(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalogue, store, imports = services(engine, tmp_path)
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"pdf data")

    def failed(entity: object) -> None:
        raise DomainError("database write failed")

    with monkeypatch.context() as patch:
        patch.setattr(catalogue.repository, "save", failed)
        with pytest.raises(DomainError):
            imports.import_file(str(source))
    assert catalogue.list_entities(Asset) == []
    assert len(list((store.root / "blobs").glob("*/*"))) == 1
    imported = imports.import_file(str(source))
    imports.verify(imported.id)
    assert len(list((store.root / "blobs").glob("*/*"))) == 1


def test_write_failure_never_creates_association(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalogue, store, imports = services(engine, tmp_path)
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"pdf data")

    def denied(*args: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "link", denied)
    with pytest.raises(AssetStoreError):
        imports.import_file(str(source))
    assert catalogue.list_entities(Asset) == []


@pytest.mark.parametrize("phase", ["copy", "before_database"])
def test_abrupt_process_exit_and_retry(engine: Engine, tmp_path: Path, phase: str) -> None:
    script = """
import os
import sys
from pathlib import Path
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.asset_imports import AssetImports
root = Path(sys.argv[1])
engine = create_database_engine(root / 'database' / 'catalogue.sqlite3')
migrate(engine)
store = LocalAssetStore(root / 'assets')
catalogue = Catalogue(SqliteCatalogue(engine), store)
if sys.argv[2] == 'copy':
    def interrupted(source, destination):
        destination.write_bytes(b'partial staged file')
        os._exit(42)
    store._copy = interrupted
else:
    catalogue.repository.save = lambda entity: os._exit(42)
AssetImports(catalogue, store).import_file(str(root / 'sheet.pdf'))
"""
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"complete original data")
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), phase], timeout=15)
    assert result.returncode == 42
    catalogue, store, imports = services(engine, tmp_path)
    assert catalogue.list_entities(Asset) == []
    if phase == "copy":
        assert len(list((store.root / ".staging").glob("*"))) == 1
        assert list((store.root / "blobs").glob("*/*")) == []
    else:
        assert len(list((store.root / "blobs").glob("*/*"))) == 1
    imported = imports.import_file(str(source))
    imports.verify(imported.id)
    destination = tmp_path / "recovered.pdf"
    imports.retrieve(imported.id, str(destination))
    assert destination.read_bytes() == source.read_bytes()
