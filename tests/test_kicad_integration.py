"""Isolated KiCad configs only: immutable copies, exact preservation and recoverable writes."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kipartmanager.application.kicad_integration import KiCadIntegration
from kipartmanager.application.publications import Publications
from kipartmanager.domain.entities import Collection, DomainError, Package, Part
from kipartmanager.infrastructure.kicad_integration import LocalKiCadIntegration
from kipartmanager.infrastructure.kicad_tables import NAMES, ROOTS, Table
from kipartmanager.infrastructure.publications import LocalPublications
from tests.test_publications import folder
from tests.test_publications import publications as publication_fixture
from tests.test_publisher import tree_files

publications = publication_fixture


@pytest.fixture
def integration(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> tuple[KiCadIntegration, LocalKiCadIntegration, Collection]:
    service, collection = publications
    assert isinstance(service.store, LocalPublications)
    adapter = LocalKiCadIntegration(
        tmp_path / "data", service.store, tmp_path / "isolated/kicad", ("9.0", "10.0")
    )
    service.publish(collection, 1)
    return KiCadIntegration(service, adapter), adapter, collection


def activate(
    case: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    version: int = 1,
    target: str = "10.0",
) -> dict[str, Any]:
    service, _, collection = case
    preview = service.prepare(str(collection.id), target, version)
    return service.activate(str(collection.id), target, preview["handle"])


def test_absent_config_and_exact_absence_backup(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    assert service.get(str(collection.id))["state"] == "UNCONFIGURED"
    result = activate(integration)
    assert result["state"] == "CURRENT" and result["active"] == 1
    _, state = adapter._state("10.0")
    journal = adapter._journal("10.0", state["operations"][0]["id"])
    assert journal["before"] == [None, None]
    assert service.verify(str(collection.id), "10.0")["verified"]


def test_lossless_third_party_comments_options_and_order() -> None:
    for i in range(2):
        raw = (
            f"# header é\r\n({ROOTS[i]}\r\n (version 7)\r\n"
            ' # keep (comment)\r\n (lib (name "Third") (type "KiCad") '
            '(uri "${ENV}/a") (options "x=y") (descr "note"))\r\n # tail\r\n)\r\n'
        ).encode()
        new = Table.read(raw, i, "9.0").updated(i, "FabParts_test", "/managed/library", None)
        assert Table.read(new, i).entry("Third") == Table.read(raw, i).entry("Third")
        assert new.startswith(raw[:-3]) and new.endswith(b")\r\n")
        assert b"# keep (comment)" in new and b"# tail\r\n" in new


def test_activation_rollback_stable_nickname_and_m7_immutable(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection], tmp_path: Path
) -> None:
    service, adapter, collection = integration
    first = activate(integration)
    historical = tree_files(folder(service.publications, collection, 1))
    cat = service.publications.publisher.catalogue
    part = cat.require(Part, collection.part_ids[0])
    cat.save(replace(part, name="Renamed"))
    renamed = replace(collection, name="New collection name")
    cat.save(renamed)
    service.publications.publisher.validation.validate(renamed)
    service.publications.publish(renamed, 2)
    assert service.get(str(collection.id), "10.0")["state"] == "UPDATE_AVAILABLE"
    assert activate(integration, 2)["active"] == 2
    assert activate(integration, 1)["active"] == 1
    assert tree_files(folder(service.publications, collection, 1)) == historical
    _, state = adapter._state("10.0")
    assert len(state["operations"]) == 3
    current = state["active"][str(collection.id)]
    assert current["nickname"] == "FabParts_" + collection.id.hex
    assert current["previous"] == 2 and first["active"] == 1
    assert len(list((adapter.root / "installed" / str(collection.id)).glob("v*/*/READY"))) == 2


def test_two_collections_do_not_replace_each_other(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    activate(integration)
    other = Collection(name="PersonalParts", part_ids=collection.part_ids)
    service.publications.publisher.catalogue.save(other)
    service.publications.publisher.validation.validate(other)
    service.publications.publish(other, 1)
    preview = service.prepare(str(other.id), "10.0", 1)
    service.activate(str(other.id), "10.0", preview["handle"])
    for i, raw in enumerate(adapter._tables("10.0")):
        assert len(Table.read(raw, i).entries) == 2


def test_nickname_collision_refused(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    target = adapter.target("10.0")
    target.mkdir(parents=True)
    raw = (
        f'(sym_lib_table (lib (name "FabParts_{collection.id.hex}") '
        '(type "KiCad") (uri "/third-party")))'
    ).encode()
    (target / NAMES[0]).write_bytes(raw)
    with pytest.raises(DomainError, match="COLLISION"):
        service.prepare(str(collection.id), "10.0", 1)
    assert (target / NAMES[0]).read_bytes() == raw and not (target / NAMES[1]).exists()


def test_external_change_after_preview_refused(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    activate(integration)
    preview = service.prepare(str(collection.id), "10.0", 1)
    path = adapter.target("10.0") / NAMES[0]
    raw = path.read_bytes() + b" \n"
    path.write_bytes(raw)
    with pytest.raises(DomainError, match="TABLE_CHANGED"):
        service.activate(str(collection.id), "10.0", preview["handle"])
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"broken",
        b"(sym_lib_table (version 99))",
        b"(sym_lib_table (future x))",
        b"();",
        b'(sym_lib_table (lib (name "X") (type "KiCad") (uri "/a") (future "x")))',
        b"\xff",
    ],
)
def test_malformed_and_unsupported_tables_refused(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection], raw: bytes
) -> None:
    service, adapter, collection = integration
    target = adapter.target("10.0")
    target.mkdir(parents=True)
    (target / NAMES[0]).write_bytes(raw)
    with pytest.raises(DomainError):
        service.prepare(str(collection.id), "10.0", 1)
    assert (target / NAMES[0]).read_bytes() == raw


def test_no_installation_configured(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    adapter.versions = ()
    assert service.get(str(collection.id))["state"] == "UNCONFIGURED"
    with pytest.raises(DomainError, match="UNAVAILABLE"):
        service.prepare(str(collection.id), "10.0", 1)


def interrupt(
    case: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kipartmanager.infrastructure.kicad_integration as module

    original = module.replace_file

    def fail_second(
        path: Path, expected: bytes | None, content: bytes | None, capture: Path
    ) -> None:
        if path.name == NAMES[1]:
            raise OSError("power loss injection")
        original(path, expected, content, capture)

    with monkeypatch.context() as patch:
        patch.setattr(module, "replace_file", fail_second)
        with pytest.raises(OSError):
            activate(case)


def test_interruption_and_explicit_restart_recovery(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, adapter, collection = integration
    interrupt(integration, monkeypatch)
    assert service.get(str(collection.id), "10.0")["state"] == "RECOVERY_REQUIRED"
    restarted = LocalKiCadIntegration(
        adapter.data_root, adapter.publications, adapter.config_root, adapter.versions
    )
    preview = restarted.recovery(collection.id, "10.0")
    result = restarted.recover(collection.id, "10.0", preview["handle"])
    assert result["state"] == "UNCONFIGURED"
    assert all(not (adapter.target("10.0") / name).exists() for name in NAMES)
    assert activate(integration)["state"] == "CURRENT"


def test_recovery_preserves_external_changes(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, adapter, collection = integration
    interrupt(integration, monkeypatch)
    path = adapter.target("10.0") / NAMES[0]
    path.write_bytes(path.read_bytes() + b"; external edit\n")
    before = tree_files(adapter.target("10.0"))
    with pytest.raises(DomainError, match="RECOVERY_CONFLICT"):
        service.recovery(str(collection.id), "10.0")
    assert tree_files(adapter.target("10.0")) == before


def test_corrupt_publication_refused_before_tables(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    (folder(service.publications, collection, 1) / "manifest.json").write_text("corrupt")
    with pytest.raises(DomainError):
        service.prepare(str(collection.id), "10.0", 1)
    assert not adapter.target("10.0").exists()


def test_permission_failure_is_safe_and_journaled(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kipartmanager.infrastructure.kicad_integration as module

    service, adapter, collection = integration
    preview = service.prepare(str(collection.id), "10.0", 1)

    def denied(*args: Any) -> None:
        raise PermissionError("test")

    monkeypatch.setattr(module, "replace_file", denied)
    with pytest.raises(PermissionError):
        service.activate(str(collection.id), "10.0", preview["handle"])
    assert not any((adapter.target("10.0") / name).exists() for name in NAMES)
    assert service.get(str(collection.id), "10.0")["state"] == "RECOVERY_REQUIRED"


def test_newer_source_format_refused_for_older_target(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    with pytest.raises(DomainError, match="KICAD_VERSION"):
        service.prepare(str(collection.id), "9.0", 1)
    assert not adapter.target("9.0").exists()


def test_model_and_datasheet_paths_are_autonomous(tmp_path: Path, engine: Any) -> None:
    from kipartmanager.application.asset_imports import AssetImports
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.domain.entities import AssetType
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from tests.test_publisher import local_probe
    from tests.test_validation import FOOTPRINT, setup_case

    fp = (
        FOOTPRINT[:-1]
        + '(model "R.wrl" (offset (xyz 1 2 3)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 90))))'
    )
    validation, resolver, part, package, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    store = local_probe(validation).store
    importer = AssetImports(validation.catalogue, store)
    for filename, data, owner, role in [
        (
            "R.wrl",
            b"#VRML V2.0 utf8\nShape { geometry Box { size 1 1 1 } }",
            package,
            AssetType.MODEL_3D,
        ),
        ("sheet.pdf", b"opaque fixture PDF", part, AssetType.DATASHEET),
    ]:
        assert isinstance(owner, (Part, Package))
        file = tmp_path / filename
        file.write_bytes(data)
        asset = importer.import_file(str(file), name=filename)
        candidate = next(
            c
            for c in resolver.search(owner, role, filename).candidates
            if c.choice.asset_id == asset.id
        )
        resolver.select(owner, candidate)
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    builder = LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data")
    publications = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "data/publications", builder),
    )
    publications.publish(collection, 1)
    assert isinstance(publications.store, LocalPublications)
    adapter = LocalKiCadIntegration(
        tmp_path / "data", publications.store, tmp_path / "isolated", ("10.0",)
    )
    integration = (KiCadIntegration(publications, adapter), adapter, collection)
    before = tree_files(folder(publications, collection, 1))
    activate(integration)
    _, state = adapter._state("10.0")
    active = state["active"][str(collection.id)]
    installed = Path(active["path"])
    assert adapter._copy(installed)
    for p in [*installed.glob("*.kicad_sym"), *installed.glob("*.pretty/*.kicad_mod")]:
        assert "${KIPRJMOD}" not in p.read_text()
        assert str(installed) in p.read_text()
    assert tree_files(folder(publications, collection, 1)) == before


def test_backup_restore_detects_external_drift_without_writing_tables(tmp_path: Path) -> None:
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.headless import open_personal_workspace
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from tests.test_publisher import local_probe
    from tests.test_validation import setup_case

    workspace = open_personal_workspace(tmp_path / "personal")
    sources = tmp_path / "sources"
    sources.mkdir()
    validation, _, part, _, collection, _ = setup_case(sources, workspace.engine)
    shutil.copytree(sources / "assets/blobs", workspace.root / "assets/blobs", dirs_exist_ok=True)
    builder = LocalLibraryBuilder(
        local_probe(validation).store, LocalKiCadIndex(workspace.root), workspace.root
    )
    publications = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(workspace.root / "publications", builder),
    )
    validation.validate(collection)
    publications.publish(collection, 1)
    assert isinstance(publications.store, LocalPublications)
    adapter = LocalKiCadIntegration(
        workspace.root, publications.store, tmp_path / "external", ("10.0",)
    )
    integration = (KiCadIntegration(publications, adapter), adapter, collection)
    activate(integration)
    backup = workspace.backup()
    part = validation.catalogue.require(Part, part.id)
    validation.catalogue.save(replace(part, name="Later"))
    validation.validate(collection)
    publications.publish(collection, 2)
    activate(integration, 2)
    external = tree_files(tmp_path / "external")
    workspace.restore(workspace.verify(Path(backup["path"]))["handle"])
    workspace.close()
    workspace = open_personal_workspace(tmp_path / "personal")
    builder = LocalLibraryBuilder(
        local_probe(validation).store, LocalKiCadIndex(workspace.root), workspace.root
    )
    history = LocalPublications(workspace.root / "publications", builder)
    restored = LocalKiCadIntegration(workspace.root, history, tmp_path / "external", ("10.0",))
    assert restored.status(collection.id, "10.0")["state"] == "RECONCILE_REQUIRED"
    assert tree_files(tmp_path / "external") == external
    assert len(history.list_publications(collection.id)) == 1
    assert list((workspace.root / "config/kicad-integration/installed").glob("*/*/*/READY"))
    # Explicit reconciliation uses only the restored M7 version, then creates fresh absolute paths.
    preview = restored.prepare(history.list_publications(collection.id)[0], "10.0")
    assert restored.activate(collection.id, "10.0", preview["handle"])["state"] == "CURRENT"
    workspace.close()


def test_ipc_readonly_restore_and_ingestion_guards(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection], engine: Any
) -> None:
    from types import SimpleNamespace

    from kipartmanager.application.catalogue_reader import CatalogueReader
    from kipartmanager.headless_ipc import respond
    from kipartmanager.infrastructure.documentation import SqliteDocumentation
    from kipartmanager.integration_ipc import validate

    service, adapter, collection = integration
    reader = CatalogueReader(
        service.publications.publisher.catalogue,
        service.publications.publisher.catalogue.repository,
        SqliteDocumentation(engine),
    )
    params = {"id": str(collection.id), "target": "10.0", "version": 1}
    request = json.dumps(
        {
            "protocol_version": 1,
            "request_id": "test",
            "method": "integration_prepare",
            "params": params,
        }
    ).encode()
    busy: Any = SimpleNamespace(preparation="busy")
    writable: Any = SimpleNamespace(preparation=None)
    restored: Any = SimpleNamespace(requires_restart=True)
    assert respond(request, reader, integration=service)["error"]["code"] == "READ_ONLY"
    assert respond(request, reader, integration=service, ingestion=busy)["error"]["code"] == "BUSY"
    assert (
        respond(
            request,
            reader,
            integration=service,
            ingestion=writable,
            workspace=restored,
        )["error"]["code"]
        == "READ_ONLY"
    )
    assert not adapter.target("10.0").exists()
    for bad in [
        {**params, "path": "/tmp"},
        {**params, "manifest": {}},
        {**params, "version": True},
        {**params, "target": "../../x"},
    ]:
        with pytest.raises((ValueError, TypeError)):
            validate("integration_prepare", bad)


def test_last_moment_external_edit_is_not_lost(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kipartmanager.infrastructure.atomic_tables as atomic

    service, adapter, collection = integration
    activate(integration)
    service.publications.publish(collection, 2)
    preview = service.prepare(str(collection.id), "10.0", 2)
    original = atomic.move
    changed = False
    path = adapter.target("10.0") / NAMES[0]
    external = path.read_bytes() + b"; last-moment external edit\n"

    def race(source: Path, target: Path, *, exchange: bool) -> None:
        nonlocal changed
        if target == path and exchange and not changed:
            changed = True
            target.write_bytes(external)
        original(source, target, exchange=exchange)

    monkeypatch.setattr(atomic, "move", race)
    with pytest.raises(DomainError, match="TABLE_CHANGED"):
        service.activate(str(collection.id), "10.0", preview["handle"])
    assert path.read_bytes() == external
    with pytest.raises(DomainError, match="RECOVERY_CONFLICT"):
        service.recovery(str(collection.id), "10.0")


def test_last_moment_creation_is_never_replaced(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kipartmanager.infrastructure.atomic_tables as atomic

    service, adapter, collection = integration
    preview = service.prepare(str(collection.id), "10.0", 1)
    original = atomic.move
    path = adapter.target("10.0") / NAMES[0]
    external = b'(sym_lib_table (lib (name "Other") (type "KiCad") (uri "/other")))'

    def race(source: Path, target: Path, *, exchange: bool) -> None:
        if target == path:
            target.write_bytes(external)
        original(source, target, exchange=exchange)

    monkeypatch.setattr(atomic, "move", race)
    with pytest.raises(FileExistsError):
        service.activate(str(collection.id), "10.0", preview["handle"])
    assert path.read_bytes() == external
    assert not (adapter.target("10.0") / NAMES[1]).exists()


def test_readonly_table_permission_respected(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    activate(integration)
    path = adapter.target("10.0") / NAMES[0]
    before = path.read_bytes()
    path.chmod(0o400)
    service.publications.publish(collection, 2)
    preview = service.prepare(str(collection.id), "10.0", 2)
    with pytest.raises(PermissionError):
        service.activate(str(collection.id), "10.0", preview["handle"])
    assert path.read_bytes() == before
    path.chmod(0o600)


def test_linked_table_and_unknown_owned_entry_are_refused(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection], tmp_path: Path
) -> None:
    service, adapter, collection = integration
    root = adapter.target("10.0")
    root.mkdir(parents=True)
    file = tmp_path / "foreign"
    file.write_text("(sym_lib_table)")
    (root / NAMES[0]).symlink_to(file)
    with pytest.raises(DomainError, match="UNSAFE_PATH"):
        service.prepare(str(collection.id), "10.0", 1)
    assert file.read_text() == "(sym_lib_table)"


def test_reactivation_reuses_verified_copy_without_table_changes(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    _, adapter, collection = integration
    activate(integration)
    paths = [adapter.target("10.0") / name for name in NAMES]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    activate(integration)
    assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    assert len(list((adapter.root / "installed" / str(collection.id)).glob("v*/*/READY"))) == 1


def test_kicad_reformat_is_preserved_but_changed_options_refused() -> None:
    raw = Table.read(None, 0).updated(0, "FabParts_test", "/v1/lib.kicad_sym", None)
    owned = Table.read(raw, 0).entry("FabParts_test")
    text = "# KiCad formatting\n" + raw.decode().replace("(lib (name", "(lib\n    (name").replace(
        '(options "")', '\n    # retain comment\n    (options "")'
    )
    result = Table.read(text.encode(), 0, "9.0").updated(
        0, "FabParts_test", "/v2/lib.kicad_sym", owned
    )
    assert b"# KiCad formatting" in result and b"# retain comment" in result
    current = Table.read(result, 0).entry("FabParts_test")
    changed = result.replace(b'(options "")', b'(options "custom")')
    with pytest.raises(DomainError, match="COLLISION"):
        Table.read(changed, 0).updated(0, "FabParts_test", "/v1/lib.kicad_sym", current)


def test_recovery_does_not_depend_on_readable_m7_history(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, adapter, collection = integration
    interrupt(integration, monkeypatch)
    (folder(service.publications, collection, 1) / "manifest.json").write_text("corrupt")
    status = service.get(str(collection.id), "10.0")
    assert status["state"] == "RECOVERY_REQUIRED" and status["publication_error"]
    preview = service.recovery(str(collection.id), "10.0")
    service.recover(str(collection.id), "10.0", preview["handle"])
    assert all(not (adapter.target("10.0") / name).exists() for name in NAMES)


def test_kicad10_refuses_legacy_comments_without_touching_tables(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
) -> None:
    service, adapter, collection = integration
    path = adapter.target("10.0") / NAMES[0]
    path.parent.mkdir(parents=True)
    raw = b"# legacy comment\n(sym_lib_table (version 7))\n"
    path.write_bytes(raw)
    assert Table.read(raw, 0).end
    with pytest.raises(DomainError, match="TABLE_FORMAT"):
        service.prepare(str(collection.id), "10.0", 1)
    assert path.read_bytes() == raw
    with pytest.raises(DomainError, match="TABLE_FORMAT"):
        Table.read(b"; not a KiCad comment\n(sym_lib_table)\n", 0)


def test_recovery_is_scoped_to_the_interrupted_collection(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, adapter, collection = integration
    other = Collection(name="Other collection")
    interrupt(integration, monkeypatch)
    before = tree_files(adapter.target("10.0"))
    with pytest.raises(DomainError, match="RECOVERY_COLLECTION_MISMATCH"):
        service.recovery(str(other.id), "10.0")
    assert not adapter.viewed
    assert tree_files(adapter.target("10.0")) == before

    preview = service.recovery(str(collection.id), "10.0")
    with pytest.raises(DomainError, match="SUMMARY_CHANGED"):
        service.recover(str(other.id), "10.0", preview["handle"])
    assert tree_files(adapter.target("10.0")) == before

    # The journal owner must be checked again at application time, independently
    # of the cached capability's collection binding.
    preview = service.recovery(str(collection.id), "10.0")
    adapter.viewed[preview["handle"]]["collection"] = str(other.id)
    with pytest.raises(DomainError, match="RECOVERY_COLLECTION_MISMATCH"):
        service.recover(str(other.id), "10.0", preview["handle"])
    assert tree_files(adapter.target("10.0")) == before
    preview = service.recovery(str(collection.id), "10.0")
    assert service.recover(str(collection.id), "10.0", preview["handle"])["state"] == "UNCONFIGURED"


@pytest.mark.parametrize("version", [1, 2])
def test_interruption_after_committed_state_requires_explicit_mirror_reconciliation(
    integration: tuple[KiCadIntegration, LocalKiCadIntegration, Collection],
    monkeypatch: pytest.MonkeyPatch,
    version: int,
) -> None:
    import kipartmanager.infrastructure.kicad_integration as module

    service, adapter, collection = integration
    if version == 2:
        activate(integration)
        service.publications.publish(collection, 2)
    _, previous = adapter._state("10.0")
    publications_before = tree_files(adapter.publications.root)
    mirror = adapter._mirror("10.0", str(collection.id))
    mirror_before = mirror.read_bytes() if mirror.exists() else None
    preview = service.prepare(str(collection.id), "10.0", version)
    from kipartmanager.infrastructure.workspace_backup import atomic_json

    original = atomic_json

    def fail_mirror(path: Path, data: dict[str, Any]) -> None:
        if path == mirror:
            raise OSError("power loss after global state commit, before workspace mirror")
        original(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(module, "atomic_json", fail_mirror)
        with pytest.raises(OSError, match="after global state commit"):
            service.activate(str(collection.id), "10.0", preview["handle"])

    _, committed = adapter._state("10.0")
    assert committed["pending"] is None
    assert committed["active"][str(collection.id)]["version"] == version
    assert committed["operations"][:-1] == previous["operations"]
    assert len(committed["operations"]) == len(previous["operations"]) + 1
    operation = committed["operations"][-1]["id"]
    journal = adapter._journal("10.0", operation)
    assert journal["next_state"] == committed and journal["previous_state"] == previous
    assert (mirror.read_bytes() if mirror.exists() else None) == mirror_before

    external = tree_files(adapter.target("10.0"))
    tables = [adapter.target("10.0") / name for name in NAMES]
    table_stats = [(p.read_bytes(), p.stat().st_mtime_ns) for p in tables]
    restarted = LocalKiCadIntegration(
        adapter.data_root, adapter.publications, adapter.config_root, adapter.versions
    )
    status = restarted.status(collection.id, "10.0")
    assert status["state"] == "RECONCILE_REQUIRED" and status["active"] == version
    assert status["operations"][0]["id"] == operation
    with pytest.raises(DomainError, match="NO_RECOVERY"):
        restarted.recovery(collection.id, "10.0")
    publication = next(
        p for p in adapter.publications.list_publications(collection.id) if p.version == version
    )
    summary = restarted.prepare(publication, "10.0")
    assert summary["reconcile"]
    assert tree_files(adapter.target("10.0")) == external
    assert (mirror.read_bytes() if mirror.exists() else None) == mirror_before

    # Only this explicit activation repairs the mirror. The same immutable copy
    # is reused, so no table replacement is needed and no committed history is lost.
    assert restarted.activate(collection.id, "10.0", summary["handle"])["state"] == "CURRENT"
    _, reconciled = restarted._state("10.0")
    assert reconciled["operations"][:-1] == committed["operations"]
    assert json.loads(mirror.read_bytes()) == {
        "operation": reconciled["operations"][-1]["id"],
        "workspace": str(adapter.data_root),
    }
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in tables] == table_stats
    assert tree_files(adapter.publications.root) == publications_before
