"""Real SQLite/store scenarios, including failures between blob publication and commit."""

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.ingestion import Ingestion, IngestionFields
from kipartmanager.application.model_jobs import ModelJobs
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.documentation import MetadataField
from kipartmanager.domain.entities import Asset, Collection, DomainError, Package, Part, PartState
from kipartmanager.headless_ipc import respond
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import migrate
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.ingestion_sandbox import open_sandbox, prepare_database
from kipartmanager.infrastructure.ingestion_transactions import (
    SqliteIngestionTransaction,
    SqliteIngestionTransactions,
)
from kipartmanager.infrastructure.model_preview import convert_mesh
from kipartmanager.infrastructure.prepared_files import LocalPreparedFiles
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews
from kipartmanager.ports.ingestion import Receipt

FIXTURES = Path(__file__).parent / "fixtures"


def compose(root: Path) -> Ingestion:
    sandbox = open_sandbox(root)
    # Keep lifetime ownership on the fixture rather than global engine state.
    sandbox.close()
    from kipartmanager.infrastructure.database import create_database_engine

    engine = create_database_engine(root / "database/catalogue.sqlite3")
    repo = SqliteCatalogue(engine)
    store = LocalAssetStore(root / "assets")
    cat = Catalogue(repo, store)
    doc = SqliteDocumentation(engine)
    preview = AssetPreviews(
        CatalogueReader(cat, repo, doc), ReadonlyPreviews(root), ModelJobs(convert_mesh)
    )
    return Ingestion(
        cat,
        doc,
        LocalResolver(cat, repo),
        SqliteIngestionTransactions(engine),
        store,
        LocalPreparedFiles(root, ReadonlyPreviews(root)),
        preview,
    )


@pytest.fixture
def ingestion(tmp_path: Path) -> Iterator[Ingestion]:
    root = tmp_path / "sandbox"
    engine = prepare_database(root)
    Catalogue(SqliteCatalogue(engine)).initialize_defaults()
    engine.dispose()
    service = compose(root)
    yield service
    service.close()
    service.previews.clear()
    assert isinstance(service.transactions, SqliteIngestionTransactions)
    service.transactions.engine.dispose()


def fields(service: Ingestion, reference: str = "TEST-03") -> IngestionFields:
    return IngestionFields(
        reference=reference,
        collections=tuple(
            str(c.id) for c in service.catalogue.list_entities(Collection) if c.name == "LabParts"
        ),
    )


def stage(service: Ingestion, preparation: str, path: Path) -> str:
    data = path.read_bytes()
    handle = service.files.start(preparation, path.name, len(data))
    for offset in range(0, len(data), 8192):
        service.files.append(preparation, handle, offset, data[offset : offset + 8192])
    service.files.finish(preparation, handle, hashlib.sha256(data).hexdigest())
    return handle


def save(
    service: Ingestion,
    begin: dict[str, Any],
    value: IngestionFields,
    selections: dict[str, str] | None = None,
    **kwargs: str,
) -> dict[str, str]:
    return service.commit(
        begin["preparation"], begin["operation_id"], value, selections or {}, **kwargs
    )


def test_minimal_metadata_resume_and_durable_receipt(ingestion: Ingestion) -> None:
    begin = ingestion.begin()
    value = replace(
        fields(ingestion), mpn="03", manufacturer="Fab", category="Timer", description="Manual"
    )
    result = save(ingestion, begin, value)
    part = ingestion.catalogue.require(Part, UUID(result["part_id"]))
    assert part.state is PartState.DRAFT and not part.asset_ids and part.package_id is None
    assert part.description == "Manual"
    identity = ingestion.documentation.identification(part.id)
    assert identity.value(MetadataField.MPN) == "03"
    assert identity.value(MetadataField.MANUFACTURER) == "Fab"
    assert identity.value(MetadataField.CATEGORY) == "Timer"
    assert identity.history[0].source.label == "Saisie utilisateur"
    assert save(ingestion, begin, value) == result  # Lost response / double confirmation.
    assert ingestion.result(begin["operation_id"]) == result
    with pytest.raises(DomainError, match="autre requête"):
        save(ingestion, begin, replace(value, reference="changed"))
    resumed = ingestion.begin(str(part.id))
    save(ingestion, resumed, replace(value, description="Completed"))
    assert ingestion.catalogue.require(Part, part.id).description == "Completed"
    assert len(ingestion.catalogue.list_entities(Part)) == 1


def test_complete_staged_previews_then_managed_files_survive_source_deletion(
    ingestion: Ingestion,
    tmp_path: Path,
) -> None:
    begin = ingestion.begin()
    preparation = begin["preparation"]
    selections = {}
    for role, fixture in (
        ("SYMBOL", "previews/Synthetic.kicad_sym"),
        ("FOOTPRINT", "previews/DIP8.kicad_mod"),
        ("MODEL_3D", "models/box.wrl"),
        ("DATASHEET", "previews/Synthetic.pdf"),
    ):
        source = tmp_path / Path(fixture).name
        source.write_bytes((FIXTURES / fixture).read_bytes())
        stage(ingestion, preparation, source)
        source.unlink()
        candidate = ingestion.search(preparation, role)["candidates"][0]
        selections[role] = candidate["token"]
        preview = ingestion.preview(preparation, candidate["token"])
        assert preview["status"] in {"ready", "loading"}
    assert ingestion.catalogue.list_entities(Asset) == []
    assert ingestion.catalogue.list_entities(Part) == []
    result = save(
        ingestion, begin, replace(fields(ingestion), package_name="DIP-8 test"), selections
    )
    part = ingestion.catalogue.require(Part, UUID(result["part_id"]))
    assert len(part.asset_ids) == 2 and part.package_id
    assert len(ingestion.catalogue.require(Package, part.package_id).asset_ids) == 2
    assets = ingestion.catalogue.list_entities(Asset)
    assert len(assets) == 4
    for asset in assets:
        assert asset.file and asset.source == asset.file.original_name
        assert asset.validation_state == "UNCHECKED" and asset.origin.value == "USER_PROVIDED"
        ingestion.store.verify(asset.file)
    for role in selections:
        assert ingestion.previews.get(str(part.id), role)["status"] in {"ready", "loading"}
    assert isinstance(ingestion.transactions, SqliteIngestionTransactions)
    engine = ingestion.transactions.engine
    engine.dispose()  # A fresh connection sees the complete state, without immutable=1.
    assert ingestion.result(begin["operation_id"]) == result
    assert ingestion.catalogue.require(Part, part.id) == part


def test_duplicates_multiple_memberships_and_explicit_variant(ingestion: Ingestion) -> None:
    value = replace(fields(ingestion), mpn="NE555", manufacturer="Test Maker")
    first = save(ingestion, ingestion.begin(), value)
    begin = ingestion.begin()
    equivalent = replace(value, reference=" test-03 ", mpn="ne555", manufacturer="test maker")
    assert (
        ingestion.inspect(begin["preparation"], equivalent)["duplicates"][0]["id"]
        == first["part_id"]
    )
    with pytest.raises(DomainError, match="Doublon"):
        save(ingestion, begin, equivalent)
    both = replace(
        value, collections=tuple(str(c.id) for c in ingestion.catalogue.list_entities(Collection))
    )
    second = save(ingestion, begin, both, action="membership", existing_id=first["part_id"])
    assert second["part_id"] == first["part_id"]
    assert len(ingestion.catalogue.list_entities(Part)) == 1
    assert all(
        UUID(first["part_id"]) in c.part_ids for c in ingestion.catalogue.list_entities(Collection)
    )
    begin = ingestion.begin()
    with pytest.raises(DomainError, match="référence distincte"):
        save(ingestion, begin, value, action="variant")
    save(
        ingestion, begin, replace(value, reference="TEST-03 extended temperature"), action="variant"
    )
    assert len(ingestion.catalogue.list_entities(Part)) == 2


def test_shared_package_preserved_and_managed_reuse(ingestion: Ingestion) -> None:
    begin = ingestion.begin()
    stage(ingestion, begin["preparation"], FIXTURES / "previews/DIP8.kicad_mod")
    token = ingestion.search(begin["preparation"], "FOOTPRINT")["candidates"][0]["token"]
    first = save(
        ingestion, begin, replace(fields(ingestion), package_name="DIP-8"), {"FOOTPRINT": token}
    )
    part = ingestion.catalogue.require(Part, UUID(first["part_id"]))
    package = ingestion.catalogue.require(Package, part.package_id)  # type: ignore[arg-type]
    choices = ingestion.catalogue.repository.choices(package)
    begin = ingestion.begin()
    value = replace(fields(ingestion, "SECOND"), package_id=str(package.id))
    info = ingestion.inspect(begin["preparation"], value)
    save(ingestion, begin, value, info["package_selections"])
    assert ingestion.catalogue.require(Package, package.id) == package
    assert len(ingestion.catalogue.list_entities(Asset)) == 1
    begin = ingestion.begin()
    stage(ingestion, begin["preparation"], FIXTURES / "previews/SOIC8.kicad_mod")
    token = ingestion.search(begin["preparation"], "FOOTPRINT")["candidates"][0]["token"]
    with pytest.raises(DomainError, match="package partagé"):
        save(ingestion, begin, replace(value, reference="THIRD"), {"FOOTPRINT": token})
    assert ingestion.catalogue.repository.choices(package) == choices
    assert len(ingestion.catalogue.list_entities(Part)) == 2
    managed = next(
        c
        for c in ingestion.search(begin["preparation"], "FOOTPRINT")["candidates"]
        if c["storage"] == "managed"
    )
    save(
        ingestion,
        begin,
        replace(value, reference="THIRD", package_id="", package_name="Variant"),
        {"FOOTPRINT": managed["token"]},
    )
    assert len(ingestion.catalogue.list_entities(Asset)) == 1


def test_rollback_keeps_only_orphan_blob_then_retry(
    ingestion: Ingestion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    begin = ingestion.begin()
    stage(ingestion, begin["preparation"], FIXTURES / "previews/Synthetic.pdf")
    candidate = ingestion.search(begin["preparation"], "DATASHEET")["candidates"][0]
    original = SqliteIngestionTransaction.record

    def fail(self: SqliteIngestionTransaction, receipt: Receipt) -> None:
        raise OSError("simulated disk full at receipt")

    monkeypatch.setattr(SqliteIngestionTransaction, "record", fail)
    with pytest.raises(OSError):
        save(ingestion, begin, fields(ingestion), {"DATASHEET": candidate["token"]})
    assert ingestion.catalogue.list_entities(Part) == []
    assert ingestion.catalogue.list_entities(Asset) == []
    assert ingestion.result(begin["operation_id"])["status"] == "not_committed"
    monkeypatch.setattr(SqliteIngestionTransaction, "record", original)
    save(ingestion, begin, fields(ingestion), {"DATASHEET": candidate["token"]})
    assert len(ingestion.catalogue.list_entities(Part)) == 1
    assert len(ingestion.catalogue.list_entities(Asset)) == 1


def test_conflicting_draft_and_cancel_preserve_canonical_assets(ingestion: Ingestion) -> None:
    first = save(ingestion, ingestion.begin(), fields(ingestion))
    begin = ingestion.begin(first["part_id"])
    part = ingestion.catalogue.require(Part, UUID(first["part_id"]))
    ingestion.catalogue.save(replace(part, description="Concurrent edit"))
    with pytest.raises(DomainError, match="brouillon a changé"):
        save(ingestion, begin, fields(ingestion))
    stage(ingestion, begin["preparation"], FIXTURES / "previews/Synthetic.pdf")
    ingestion.cancel(begin["preparation"])
    assert len(ingestion.catalogue.list_entities(Part)) == 1
    assert ingestion.catalogue.list_entities(Asset) == []
    with pytest.raises(DomainError):
        save(ingestion, begin, fields(ingestion))


def test_transfer_bounds_order_corruption_expiry(
    ingestion: Ingestion, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin = ingestion.begin()
    prep = begin["preparation"]
    for name, size in (
        ("../personal.pdf", 4),
        ("test.exe", 4),
        ("big.pdf", 17 * 1024 * 1024),
        ("zero.pdf", 0),
    ):
        with pytest.raises(DomainError):
            ingestion.files.start(prep, name, size)
    handle = ingestion.files.start(prep, "bad.pdf", 4)
    with pytest.raises(DomainError):
        ingestion.files.append(prep, handle, 1, b"bad!")
    ingestion.files.append(prep, handle, 0, b"bad!")
    with pytest.raises(DomainError):
        ingestion.files.finish(prep, handle, "0" * 64)
    with pytest.raises(DomainError):
        ingestion.files.finish(prep, handle, hashlib.sha256(b"bad!").hexdigest())
    ingestion.files.discard(prep, handle)
    assert isinstance(ingestion.files, LocalPreparedFiles)
    ingestion.files.sessions[prep].created -= 1201
    with pytest.raises(DomainError, match="expirée"):
        ingestion.search(prep, "SYMBOL")
    assert not tuple(ingestion.files.root.iterdir())


def test_sandbox_refuses_unmarked_symlinks_readonly_and_second_writer(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    with pytest.raises(DomainError):
        open_sandbox(root)
    engine = prepare_database(root)
    engine.dispose()
    with pytest.raises(DomainError):
        prepare_database(root)
    first = open_sandbox(root)
    try:
        assert first.backup.joinpath("catalogue.sqlite3").is_file()
        with pytest.raises(DomainError, match="déjà ouvert"):
            open_sandbox(root)
    finally:
        first.close()
    link = root / "assets/forbidden"
    link.symlink_to(tmp_path)
    with pytest.raises(DomainError, match="Lien"):
        open_sandbox(root)
    link.unlink()
    (root / "TECH01_COPY.json").write_text("{}")
    with pytest.raises(DomainError, match="readonly"):
        open_sandbox(root)


def test_receipt_migration_preserves_prior_data_and_refuses_loss(ingestion: Ingestion) -> None:
    assert isinstance(ingestion.transactions, SqliteIngestionTransactions)
    engine = ingestion.transactions.engine
    migrate(engine, "0007_asset_provenance", downgrade=True)
    old = Part(name="Pre-TECH03")
    ingestion.catalogue.save(old)
    migrate(engine)
    assert ingestion.catalogue.require(Part, old.id) == old
    save(ingestion, ingestion.begin(), fields(ingestion))
    with pytest.raises(RuntimeError, match="receipts"):
        migrate(engine, "0007_asset_provenance", downgrade=True)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM ingestion_operations")) == 1
        assert c.scalar(text("PRAGMA integrity_check")) == "ok"


def test_ipc_readonly_gate_and_strict_writable_params(ingestion: Ingestion) -> None:
    reader = ingestion.previews.catalogue

    def call(method: str, params: dict[str, Any], writable: bool = True) -> dict[str, Any]:
        return respond(
            json.dumps(
                {"protocol_version": 1, "request_id": "test", "method": method, "params": params}
            ).encode(),
            reader,
            ingestion.previews,
            ingestion if writable else None,
        )

    assert call("ingestion_begin", {}, False)["error"]["code"] == "READ_ONLY"
    assert call("ingestion_begin", {"path": "/anywhere"})["error"]["code"] == "INVALID_PARAMS"
    assert (
        call("ingestion_file_start", {"preparation": "x", "filename": "x.pdf", "size": True})[
            "error"
        ]["code"]
        == "INVALID_PARAMS"
    )
    assert call("ingestion_begin", {})["ok"]
    assert call("health", {})["result"]["read_only"] is False


def test_real_headless_restart_confirmation_and_backup(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    engine = prepare_database(root)
    cat = Catalogue(SqliteCatalogue(engine))
    cat.initialize_defaults()
    value = {"reference": "IPC-03", "collections": [str(cat.list_entities(Collection)[0].id)]}
    engine.dispose()
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}

    def launch() -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-m", "kipartmanager.headless", "--data-dir", str(root), "--sandbox"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def call(child: subprocess.Popen[str], method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert child.stdin and child.stdout
        child.stdin.write(
            json.dumps(
                {
                    "protocol_version": 1,
                    "request_id": str(uuid4()),
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        child.stdin.flush()
        result = json.loads(child.stdout.readline())
        assert result["ok"], result
        return result["result"]  # type: ignore[no-any-return]

    child = launch()
    try:
        begin = call(child, "ingestion_begin", {})
        assert call(child, "health", {})["qt_loaded"] is False
        saved = call(
            child,
            "ingestion_commit",
            {
                "preparation": begin["preparation"],
                "operation_id": begin["operation_id"],
                "fields": value,
                "selections": {},
            },
        )
        child.kill()  # Commit survived an abrupt shutdown before a clean shutdown handshake.
        child.wait(timeout=10)
        child = launch()
        assert call(child, "ingestion_result", {"operation_id": begin["operation_id"]}) == saved
        assert call(child, "get_component", {"id": saved["part_id"]})["reference"] == "IPC-03"
        call(child, "shutdown", {})
        assert child.wait(timeout=10) == 0
        assert len(list((root / "backups").iterdir())) == 2
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_official_reference_reuse_and_unchanged_library(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.domain.kicad import LibraryRoots
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex

    assert isinstance(ingestion.files, LocalPreparedFiles)
    root = ingestion.files.root.parent
    official = tmp_path / "official"
    official.mkdir()
    symbol = official / "Synthetic.kicad_sym"
    source = (FIXTURES / "previews/Synthetic.kicad_sym").read_bytes()
    symbol.write_bytes(source)
    index = LocalKiCadIndex(root)
    index.configure(LibraryRoots(symbols=str(official)))
    index.rebuild(index.configuration())
    libraries = KiCadLibraries(index)
    ingestion.libraries = libraries
    ingestion.resolver.libraries = libraries
    begin = ingestion.begin()
    candidate = ingestion.search(begin["preparation"], "SYMBOL")["candidates"][0]
    assert candidate["origin"] == "KICAD_OFFICIAL"
    assert ingestion.preview(begin["preparation"], candidate["token"])["drawings"]
    result = save(ingestion, begin, fields(ingestion), {"SYMBOL": candidate["token"]})
    assert not ingestion.catalogue.list_entities(Asset)
    part = ingestion.catalogue.require(Part, UUID(result["part_id"]))
    assert ingestion.catalogue.repository.choices(part)[0].reference
    assert symbol.read_bytes() == source
    assert ingestion.previews.get(str(part.id), "SYMBOL")["status"] == "ready"


def test_equal_content_distinct_assets_and_early_store_failure(
    ingestion: Ingestion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ingestion.store.import_content

    def fail(content: bytes, filename: str) -> Any:
        raise OSError("simulated ENOSPC")

    for index in range(2):
        begin = ingestion.begin()
        stage(ingestion, begin["preparation"], FIXTURES / "previews/Synthetic.pdf")
        token = ingestion.search(begin["preparation"], "DATASHEET")["candidates"][0]["token"]
        monkeypatch.setattr(ingestion.store, "import_content", fail)
        with pytest.raises(OSError):
            save(ingestion, begin, fields(ingestion, str(index)), {"DATASHEET": token})
        assert len(ingestion.catalogue.list_entities(Part)) == index
        monkeypatch.setattr(ingestion.store, "import_content", original)
        save(ingestion, begin, fields(ingestion, str(index)), {"DATASHEET": token})
    assets = ingestion.catalogue.list_entities(Asset)
    assert len(assets) == 2 and assets[0].id != assets[1].id
    assert assets[0].file == assets[1].file
    assert isinstance(ingestion.files, LocalPreparedFiles)
    assert len(list((ingestion.files.root.parent / "assets/blobs").glob("*/*"))) == 1


def test_staged_missing_modified_and_restart_cleanup(ingestion: Ingestion) -> None:
    begin = ingestion.begin()
    handle = stage(ingestion, begin["preparation"], FIXTURES / "previews/Synthetic.pdf")
    assert isinstance(ingestion.files, LocalPreparedFiles)
    path = ingestion.files.root / begin["preparation"] / handle
    data = path.read_bytes()
    path.write_bytes(b"x" * len(data))
    with pytest.raises(DomainError, match="modifié"):
        ingestion.files.content(begin["preparation"], handle)
    path.unlink()
    with pytest.raises(OSError):
        ingestion.files.content(begin["preparation"], handle)
    root = ingestion.files.root.parent
    sandbox = open_sandbox(root)
    try:
        assert not tuple((root / "preparations").iterdir())
        assert not ingestion.catalogue.list_entities(Part)
    finally:
        sandbox.close()
    ingestion.files.sessions.clear()


def test_restore_retains_backup_and_committed_result(ingestion: Ingestion, tmp_path: Path) -> None:
    from kipartmanager.infrastructure.ingestion_sandbox import restore_backup

    begin = ingestion.begin()
    saved = save(ingestion, begin, fields(ingestion))
    assert isinstance(ingestion.files, LocalPreparedFiles)
    sandbox = open_sandbox(ingestion.files.root.parent)
    backup = sandbox.backup
    sandbox.close()
    before = {p.relative_to(backup): p.read_bytes() for p in backup.rglob("*") if p.is_file()}
    engine = restore_backup(backup, tmp_path / "restored")
    try:
        assert SqliteCatalogue(engine).get(Part, UUID(saved["part_id"]))
        assert SqliteIngestionTransactions(engine).receipt(UUID(begin["operation_id"]))
    finally:
        engine.dispose()
    assert before == {
        p.relative_to(backup): p.read_bytes() for p in backup.rglob("*") if p.is_file()
    }


def test_removing_prepared_file_revokes_candidates_without_creating_assets(
    ingestion: Ingestion,
) -> None:
    begin = ingestion.begin()
    prep = begin["preparation"]
    handle = stage(ingestion, prep, FIXTURES / "previews/Synthetic.kicad_sym")
    candidates = ingestion.search(prep, "SYMBOL")["candidates"]
    assert len(candidates) > 1
    removed = ingestion.remove(prep, handle)["removed"]
    assert set(removed) == {c["token"] for c in candidates}
    for token in removed:
        with pytest.raises(DomainError):
            ingestion.preview(prep, token)
    assert ingestion.search(prep, "SYMBOL")["candidates"] == []
    assert not ingestion.catalogue.list_entities(Asset)
    save(ingestion, begin, fields(ingestion))


def test_partial_draft_resume_retains_existing_choices(ingestion: Ingestion) -> None:
    begin = ingestion.begin()
    choices = {}
    for role, name in [("SYMBOL", "Synthetic.kicad_sym"), ("DATASHEET", "Synthetic.pdf")]:
        stage(ingestion, begin["preparation"], FIXTURES / "previews" / name)
        choices[role] = ingestion.search(begin["preparation"], role)["candidates"][0]["token"]
    saved = save(ingestion, begin, fields(ingestion), choices)
    resumed = ingestion.begin(saved["part_id"])
    with pytest.raises(DomainError):
        save(ingestion, resumed, fields(ingestion), {})
    result = save(
        ingestion,
        resumed,
        replace(fields(ingestion), description="Completed later"),
        resumed["selections"],
    )
    part = ingestion.catalogue.require(Part, UUID(result["part_id"]))
    assert part.package_id is None and len(part.asset_ids) == 2
    assert len(ingestion.catalogue.list_entities(Asset)) == 2
    assert part.description == "Completed later"


def test_sandbox_accepts_internal_publication_links_but_refuses_external_links(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sandbox"
    prepare_database(root).dispose()
    stage = root / "assets" / "interrupted-stage"
    stage.write_bytes(b"published but staging not yet unlinked")
    blob = root / "assets" / "published"
    os.link(stage, blob)
    sandbox = open_sandbox(root)
    sandbox.close()
    assert stage.read_bytes() == blob.read_bytes()
    outside = tmp_path / "outside"
    os.link(blob, outside)
    with pytest.raises(DomainError, match="extérieur"):
        open_sandbox(root)
    assert outside.read_bytes() == stage.read_bytes()


def test_process_exit_before_transaction_commit_leaves_only_orphan_blob(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    engine = prepare_database(root)
    Catalogue(SqliteCatalogue(engine)).initialize_defaults()
    engine.dispose()
    code = """
import os, sys
from pathlib import Path
from test_ingestion import compose, fields, stage, save, FIXTURES
from kipartmanager.infrastructure.ingestion_transactions import SqliteIngestionTransaction
service = compose(Path(sys.argv[1]))
begin = service.begin()
stage(service, begin['preparation'], FIXTURES / 'previews/Synthetic.pdf')
token = service.search(begin['preparation'], 'DATASHEET')['candidates'][0]['token']
def interrupted(self, receipt):
    os._exit(23)
SqliteIngestionTransaction.record = interrupted
save(service, begin, fields(service), {'DATASHEET':token})
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(Path("src").resolve()), str(Path("tests").resolve())]),
    }
    child = subprocess.run(
        [sys.executable, "-c", code, str(root)], env=env, timeout=30, capture_output=True
    )
    assert child.returncode == 23, child.stderr.decode()
    assert tuple(
        (root / "assets/blobs").glob("*/*")
    )  # Published bytes survive; never auto-deleted.
    sandbox = open_sandbox(root)
    try:
        assert not SqliteCatalogue(sandbox.engine).list_entities(Part)
        assert not SqliteCatalogue(sandbox.engine).list_entities(Asset)
        with sandbox.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM ingestion_operations").scalar()
                == 0
            )
    finally:
        sandbox.close()


def test_whitespace_reference_uses_mpn_for_duplicate_identity(ingestion: Ingestion) -> None:
    save(ingestion, ingestion.begin(), fields(ingestion, "MPN-ONLY"))
    begin = ingestion.begin()
    value = replace(fields(ingestion), reference="   ", mpn="MPN-ONLY")
    assert ingestion.inspect(begin["preparation"], value)["duplicates"]
    with pytest.raises(DomainError, match="Doublon"):
        save(ingestion, begin, value)
    assert len(ingestion.catalogue.list_entities(Part)) == 1


def test_resumed_draft_saves_exact_selected_memberships_and_detects_changes(
    ingestion: Ingestion,
) -> None:
    collections = ingestion.catalogue.list_entities(Collection)
    assert len(collections) == 2
    value = replace(fields(ingestion), collections=tuple(str(c.id) for c in collections))
    saved = save(ingestion, ingestion.begin(), value)
    part_id = UUID(saved["part_id"])
    begin = ingestion.begin(saved["part_id"])
    save(ingestion, begin, replace(value, collections=(str(collections[1].id),)))
    assert part_id not in ingestion.catalogue.require(Collection, collections[0].id).part_ids
    assert part_id in ingestion.catalogue.require(Collection, collections[1].id).part_ids
    begin = ingestion.begin(saved["part_id"])
    ingestion.catalogue.save(replace(collections[0], part_ids=(part_id,)))
    with pytest.raises(DomainError, match="brouillon a changé"):
        save(ingestion, begin, value)
