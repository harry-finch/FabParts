"""Personal workspace lifecycle, complete authority snapshots and interrupted recovery."""

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.ingestion import Ingestion
from kipartmanager.application.model_jobs import ModelJobs
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset, Collection, DomainError, Part
from kipartmanager.headless import open_personal_workspace as open_user
from kipartmanager.headless_ipc import respond
from kipartmanager.infrastructure import user_workspace as user
from kipartmanager.infrastructure import workspace_backup as backup
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.ingestion_transactions import SqliteIngestionTransactions
from kipartmanager.infrastructure.model_preview import convert_mesh
from kipartmanager.infrastructure.prepared_files import LocalPreparedFiles
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews
from tests.test_ingestion import FIXTURES, fields, save, stage


def compose(workspace: user.UserWorkspace) -> Ingestion:
    root, engine = workspace.root, workspace.engine
    repo = SqliteCatalogue(engine)
    store = LocalAssetStore(root / "assets")
    cat = Catalogue(repo, store)
    doc = SqliteDocumentation(engine)
    previews = AssetPreviews(
        CatalogueReader(cat, repo, doc), ReadonlyPreviews(root), ModelJobs(convert_mesh)
    )
    return Ingestion(
        cat,
        doc,
        LocalResolver(cat, repo),
        SqliteIngestionTransactions(engine),
        store,
        LocalPreparedFiles(root, ReadonlyPreviews(root)),
        previews,
    )


def close(service: Ingestion, workspace: user.UserWorkspace) -> None:
    service.previews.clear()
    service.close()
    workspace.close()


def populate(workspace: user.UserWorkspace) -> tuple[str, dict[str, str]]:
    service = compose(workspace)
    begin = service.begin()
    selected = {}
    for role, file in [
        ("SYMBOL", "previews/Synthetic.kicad_sym"),
        ("FOOTPRINT", "previews/DIP8.kicad_mod"),
        ("MODEL_3D", "models/box.wrl"),
        ("DATASHEET", "previews/Synthetic.pdf"),
    ]:
        stage(service, begin["preparation"], FIXTURES / file)
        selected[role] = service.search(begin["preparation"], role)["candidates"][0]["token"]
    result = save(
        service, begin, replace(fields(service), package_name="Persistent DIP-8"), selected
    )
    part_id = result["part_id"]
    assert len(service.catalogue.list_entities(Asset)) == 4
    service.previews.clear()
    service.close()
    return part_id, result


def test_first_start_defaults_restart_no_automatic_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "personal"
    monkeypatch.setattr(user, "default_home", lambda: home)
    workspace = open_user()
    root = workspace.root
    service = compose(workspace)
    assert len(service.catalogue.list_entities(Collection)) == 2
    result = save(service, service.begin(), fields(service))
    close(service, workspace)
    again = open_user()
    assert again.root == root and not tuple((home / "backups").iterdir())
    service = compose(again)
    assert service.result(result["operation_id"]) == result
    assert service.catalogue.require(Part, UUID(result["part_id"])).state.value == "DRAFT"
    close(service, again)


def test_complete_backup_restore_and_four_previews(tmp_path: Path) -> None:
    workspace = open_user(tmp_path / "personal")
    part, result = populate(workspace)
    (workspace.root / "config/example.toml").write_text("example=true")
    # A real publication, including its retained dependencies and COMMIT.
    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications
    from tests.test_publisher import local_probe
    from tests.test_validation import setup_case

    (tmp_path / "publishing").mkdir()
    validation, _, _, _, collection, _ = setup_case(tmp_path / "publishing", workspace.engine)
    builder = LocalLibraryBuilder(
        local_probe(validation).store,
        LocalKiCadIndex(tmp_path / "publishing/data"),
        tmp_path / "publishing/data",
    )
    validation.validate(collection)
    pub = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(workspace.root / "publications", builder),
    )
    version = pub.publish(collection, 1)
    # Materialize the publication fixture’s canonical blobs in this test workspace.
    import shutil

    source = local_probe(validation).store.root
    shutil.copytree(source / "blobs", workspace.root / "assets/blobs", dirs_exist_ok=True)
    saved = workspace.backup()
    path = Path(saved["path"])
    manifest = backup.verify_backup(path)
    assert any(name.endswith("/manifest.json") for name in manifest["files"])
    assert any("/inputs/" in name for name in manifest["files"])
    original_root = workspace.root
    before = backup.inventory(path)
    handle = workspace.verify(path)["handle"]
    restored = workspace.restore(handle)
    assert restored["restart_required"] and original_root.is_dir()
    assert backup.inventory(path) == before
    workspace.close()
    workspace = open_user(tmp_path / "personal")
    assert workspace.root != original_root
    service = compose(workspace)
    assert service.result(result["operation_id"]) == result
    for role in ("SYMBOL", "FOOTPRINT", "MODEL_3D", "DATASHEET"):
        assert service.previews.get(part, role)["status"] in {"ready", "loading"}
    assert (workspace.root / "config/example.toml").read_text() == "example=true"
    assert len(service.catalogue.list_entities(Asset)) >= 4
    # Publication identity and retained dependencies survive unchanged.
    rebuilt_store = LocalPublications(workspace.root / "publications", builder)
    rebuilt_store.verify(version)
    assert backup.inventory(path) == before
    close(service, workspace)


def test_second_writer_unrecognized_and_permissions(tmp_path: Path) -> None:
    home = tmp_path / "personal"
    workspace = open_user(home)
    with pytest.raises(DomainError, match="déjà ouvert"):
        open_user(home)
    workspace.close()
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "personal.txt").write_text("do not touch")
    with pytest.raises(DomainError):
        open_user(unknown)
    assert (unknown / "personal.txt").read_text() == "do not touch"
    link = tmp_path / "linked"
    link.symlink_to(home)
    with pytest.raises(DomainError):
        open_user(link)
    home.chmod(0o500)
    try:
        with pytest.raises((PermissionError, DomainError)):
            open_user(home)
    finally:
        home.chmod(0o700)


def test_migration_0007_backed_up_verified_before_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "personal"
    workspace = open_user(home)
    root = workspace.root
    workspace.close()
    engine = create_database_engine(root / "database/catalogue.sqlite3")
    migrate(engine, "0007_asset_provenance", downgrade=True)
    engine.dispose()
    original = migrate

    def migrate_checked(*args: Any, **kwargs: Any) -> None:
        backups = list((home / "backups").iterdir())
        assert len(backups) == 1
        assert backup.verify_backup(backups[0])["schema"] == "0007_asset_provenance"
        original(*args, **kwargs)

    monkeypatch.setattr(user, "migrate", migrate_checked)
    workspace = open_user(home)
    assert (
        backup.database_schema(root / "database/catalogue.sqlite3") == "0008_ingestion_operations"
    )
    workspace.close()


@pytest.mark.parametrize("version", ["unknown", "9999_future"])
def test_unknown_schema_never_changes_catalogue(tmp_path: Path, version: str) -> None:
    home = tmp_path / "personal"
    workspace = open_user(home)
    root = workspace.root
    workspace.close()
    db = root / "database/catalogue.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE alembic_version SET version_num=?", (version,))
    before = db.read_bytes()
    with pytest.raises(DomainError):
        open_user(home)
    assert db.read_bytes() == before and not tuple((home / "backups").iterdir())


@pytest.mark.parametrize(
    "change", ["bytes", "extra", "missing", "manifest", "partial", "symlink", "hardlink"]
)
def test_corrupt_incomplete_or_linked_backups_refused(tmp_path: Path, change: str) -> None:
    workspace = open_user(tmp_path / "personal")
    populate(workspace)
    path = Path(workspace.backup()["path"])
    root = workspace.root
    manifest = backup.verify_backup(path)
    name = next(n for n in manifest["files"] if n.startswith("assets/"))
    if change == "bytes":
        (path / name).write_bytes(b"changed")
    elif change == "extra":
        (path / "assets/extra").write_bytes(b"foreign")
    elif change == "missing":
        (path / name).unlink()
    elif change == "manifest":
        (path / "manifest.json").write_text("{broken")
    elif change == "partial":
        path = path.rename(path.with_name(".partial-" + path.name))
    elif change == "symlink":
        (path / "linked").symlink_to(root)
    elif change == "hardlink":
        os.link(path / name, tmp_path / "external-link")
    with pytest.raises((DomainError, OSError)):
        workspace.verify(path)
    assert workspace.root == root and not workspace.requires_restart
    workspace.close()


@pytest.mark.parametrize("operation", ["backup", "restore", "migration"])
def test_interruptions_preserve_active_and_cannot_publish_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    workspace = open_user(tmp_path / "personal")
    populate(workspace)
    source = Path(workspace.backup()["path"])
    root = workspace.root
    pointer = (workspace.home / "active.json").read_bytes()
    db = (root / "database/catalogue.sqlite3").read_bytes()
    handle = workspace.verify(source)["handle"]
    if operation == "migration":
        workspace.close()
        engine = create_database_engine(root / "database/catalogue.sqlite3")
        # Use an otherwise empty personal workspace for a receipt-free downgrade.
        clean = open_user(tmp_path / "migration")
        clean_root = clean.root
        clean.close()
        ce = create_database_engine(clean_root / "database/catalogue.sqlite3")
        migrate(ce, "0007_asset_provenance", downgrade=True)
        ce.dispose()

        def failing_migration(*args: Any, **kwargs: Any) -> None:
            raise OSError("ENOSPC")

        monkeypatch.setattr(user, "migrate", failing_migration)
        with pytest.raises(OSError):
            open_user(tmp_path / "migration")
        assert (
            backup.database_schema(clean_root / "database/catalogue.sqlite3")
            == "0007_asset_provenance"
        )
        assert backup.verify_backup(next((tmp_path / "migration/backups").iterdir()))
        engine.dispose()
        return
    original_copy = backup.copy_file

    def interrupted(src: Path, dst: Path) -> None:
        original_copy(src, dst)
        if operation == "backup" or ".restoring-" in str(dst):
            raise OSError("ENOSPC")

    monkeypatch.setattr(backup, "copy_file", interrupted)
    with pytest.raises(OSError):
        workspace.backup() if operation == "backup" else workspace.restore(handle)
    assert (workspace.home / "active.json").read_bytes() == pointer
    assert (root / "database/catalogue.sqlite3").read_bytes() == db
    for partial in (workspace.home / "backups").glob(".partial-*"):
        with pytest.raises(DomainError):
            backup.verify_backup(partial)
    workspace.close()


def test_missing_canonical_blob_refused_and_manifest_changed_after_selection(
    tmp_path: Path,
) -> None:
    workspace = open_user(tmp_path / "personal")
    populate(workspace)
    path = Path(workspace.backup()["path"])
    handle = workspace.verify(path)["handle"]
    (path / "manifest.json").write_text("{}")
    with pytest.raises(DomainError):
        workspace.restore(handle)
    next((workspace.root / "assets/blobs").glob("*/*")).unlink()
    with pytest.raises(DomainError):
        workspace.backup()
    workspace.close()


def test_workspace_ipc_rejects_paths_for_restore_and_readonly(tmp_path: Path) -> None:
    workspace = open_user(tmp_path / "personal")
    service = compose(workspace)
    reader = CatalogueReader(service.catalogue, service.catalogue.repository, service.documentation)

    def call(method: str, params: dict[str, str], personal: bool = True) -> dict[str, Any]:
        return respond(
            json.dumps(
                {"protocol_version": 1, "request_id": "test", "method": method, "params": params}
            ).encode(),
            reader,
            service.previews,
            service,
            "0008_ingestion_operations",
            workspace if personal else None,
        )

    assert call("workspace_info", {})["ok"]
    assert call("workspace_backup", {}, False)["error"]["code"] == "READ_ONLY"
    assert call("workspace_restore", {"path": "/arbitrary"})["error"]["code"] == "INVALID_PARAMS"
    assert call("workspace_restore", {"handle": "unknown"})["ok"] is False
    close(service, workspace)


@pytest.mark.parametrize("operation", ["backup", "restore", "migration"])
def test_process_exit_releases_lock_and_preserves_active(tmp_path: Path, operation: str) -> None:
    """A killed process cannot activate an incomplete snapshot or hold the writer lock."""
    import subprocess
    import sys

    home = tmp_path / "personal"
    workspace = open_user(home)
    populate(workspace)
    source = workspace.backup()["path"]
    root = workspace.root
    workspace.close()
    if operation == "migration":
        # Model a 0007 catalogue with assets but without 0008 receipts.
        with sqlite3.connect(root / "database/catalogue.sqlite3") as db:
            db.execute("DELETE FROM ingestion_operations")
        engine = create_database_engine(root / "database/catalogue.sqlite3")
        migrate(engine, "0007_asset_provenance", downgrade=True)
        engine.dispose()
    pointer = (home / "active.json").read_bytes()
    before = (root / "database/catalogue.sqlite3").read_bytes()
    script = """
import os, sys
from pathlib import Path
from kipartmanager.headless import open_personal_workspace
from kipartmanager.infrastructure import workspace_backup as backup, user_workspace as user
home, source, operation = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
original = backup.copy_file
def terminate(src, dst):
    original(src, dst)
    if operation == 'backup' or '.restoring-' in str(dst):
        os._exit(77)
if operation == 'migration':
    def interrupted(*args, **kwargs):
        os._exit(77)
    user.migrate = interrupted
else:
    backup.copy_file = terminate
workspace = open_personal_workspace(home)
if operation == 'backup': workspace.backup()
if operation == 'restore': workspace.restore(workspace.verify(source)['handle'])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(home), source, operation], timeout=30
    )
    assert result.returncode == 77
    assert (home / "active.json").read_bytes() == pointer
    assert (root / "database/catalogue.sqlite3").read_bytes() == before
    for partial in (home / "backups").glob(".partial-*"):
        with pytest.raises(DomainError):
            backup.verify_backup(partial)
    # The OS lock was released, and opening recovers the same active generation.
    again = open_user(home)
    assert again.root == root
    assert len(compose(again).catalogue.list_entities(Asset)) == 4
    again.close()
