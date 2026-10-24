"""Offline two-machine transfer, hostile archives, conflicts and transaction failures."""

import json
import shutil
import socket
import stat
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, delete
from sqlalchemy.exc import OperationalError

from kipartmanager.application.publications import Publications
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.domain.entities import Asset, Collection, DomainError, Package, Part
from kipartmanager.domain.publication import Publication
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.bundles import LocalBundles
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.infrastructure.publications import LocalPublications
from tests.test_publisher import local_probe, tree_files
from tests.test_validation import setup_case


@pytest.fixture
def publications(tmp_path: Path, engine: Engine) -> tuple[Publications, Collection]:
    validation, _, _, _, collection, _ = setup_case(tmp_path, engine)
    store = local_probe(validation).store
    builder = LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data")
    validation.validate(collection)
    return Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "data/publications", builder),
    ), collection


@pytest.fixture
def target(tmp_path: Path) -> Iterator[LocalBundles]:
    root = tmp_path / "target"
    engine = create_database_engine(root / "database.sqlite3")
    migrate(engine)
    store = LocalAssetStore(root / "assets")
    history = LocalPublications(
        root / "publications", LocalLibraryBuilder(store, LocalKiCadIndex(root), root)
    )
    transport = LocalBundles(SqliteCatalogue(engine), history)
    yield transport
    engine.dispose()


def exported(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> tuple[LocalBundles, Path, Publication]:
    service, collection = publications
    publication = service.publish(collection, 7)
    assert isinstance(service.publisher.catalogue.repository, SqliteCatalogue)
    assert isinstance(service.store, LocalPublications)
    transport = LocalBundles(service.publisher.catalogue.repository, service.store)
    archive = tmp_path / "library.kiparts"
    transport.export(publication, str(archive))
    return transport, archive, publication


def rewrite(source: Path, destination: Path, change: Callable[[dict[str, bytes]], None]) -> None:
    with zipfile.ZipFile(source) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    change(contents)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, encoded in contents.items():
            archive.writestr(name, encoded)


def test_roundtrip_without_source_or_network(
    publications: tuple[Publications, Collection],
    target: LocalBundles,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    source, archive, publication = exported(publications, tmp_path)
    saved = tree_files(source.publications._folder(publication.collection_id, 7))
    preview = target.inspect(str(archive))
    assert preview.can_import and (preview.parts, preview.packages, preview.assets) == (1, 1, 2)
    source_entities = source.repository.list_entities(Asset)
    shutil.rmtree(source.publications.root)
    shutil.rmtree(source.store.root)
    result = target.import_bundle(str(archive))
    assert result == preview
    assert target.publications.list_publications() == (publication,)
    target.publications.verify(publication)
    assert tree_files(target.publications._folder(publication.collection_id, 7)) == saved
    assert {a.id: (a.file, a.origin) for a in target.repository.list_entities(Asset)} == {
        a.id: (a.file, a.origin) for a in source_entities
    }
    part = target.repository.list_entities(Part)[0]
    assert len(target.repository.choices(part)) == 1
    rebuilt = target.publications.rebuild(publication, str(tmp_path / "rebuilt"))
    assert tree_files(Path(rebuilt.destination)) == {
        k.removeprefix("artifacts/"): v for k, v in saved.items() if k.startswith("artifacts/")
    }
    assert b"/Users/" not in b"".join(tree_files(Path(rebuilt.destination)).values())
    # Repeated import is idempotent and doesn't replace existing objects.
    assert target.import_bundle(str(archive)).can_import
    assert len(target.repository.list_entities(Part)) == 1
    second = tmp_path / "again.kiparts"
    target.export(publication, str(second))
    assert target.inspect(str(second)).can_import


@pytest.mark.parametrize(
    "kind", ["asset", "part", "package", "collection", "choice", "name", "version"]
)
def test_explicit_conflicts_leave_destination_unchanged(
    publications: tuple[Publications, Collection], target: LocalBundles, tmp_path: Path, kind: str
) -> None:
    _, archive, publication = exported(publications, tmp_path)
    target.import_bundle(str(archive))
    repo = target.repository
    if kind == "asset":
        entity = repo.list_entities(Asset)[0]
        repo.save(replace(entity, name="Different"))
    elif kind in {"part", "package", "collection"}:
        entity = repo.list_entities(
            {"part": Part, "package": Package, "collection": Collection}[kind]
        )[0]
        repo.save(replace(entity, name="Different"))
    elif kind == "choice":
        part = repo.list_entities(Part)[0]
        with repo.engine.begin() as connection:
            from kipartmanager.infrastructure.models import ChoiceRow

            connection.execute(delete(ChoiceRow).where(ChoiceRow.part_id == part.id))
    elif kind == "name":
        repo = target.repository
        collection = repo.list_entities(Collection)[0]
        repo.save(replace(collection, name="Renamed"))
        repo.save(Collection(id=uuid4(), name=publication.collection_name))
    else:
        (target.publications._folder(publication.collection_id, 7) / "COMMIT").write_text("bad")
    before = {k: target.repository.list_entities(k) for k in (Asset, Part, Package, Collection)}
    preview = target.inspect(str(archive))
    assert not preview.can_import and preview.conflicts
    with pytest.raises(DomainError, match="conflits"):
        target.import_bundle(str(archive))
    assert {k: repo.list_entities(k) for k in before} == before


@pytest.mark.parametrize(
    "attack",
    [
        "hash",
        "extra",
        "missing",
        "schema",
        "traversal",
        "absolute",
        "backslash",
        "colon",
        "duplicate",
        "symlink",
        "json_duplicate",
        "huge",
    ],
)
def test_hostile_archives_rejected_without_writes(
    publications: tuple[Publications, Collection], target: LocalBundles, tmp_path: Path, attack: str
) -> None:
    _, archive, _ = exported(publications, tmp_path)
    bad = tmp_path / "bad.kiparts"

    def change(contents: dict[str, bytes]) -> None:
        if attack == "hash":
            name = next(n for n in contents if n.startswith("publication/inputs/"))
            contents[name] += b"changed"
        elif attack == "missing":
            del contents["publication/COMMIT"]
        elif attack == "schema":
            data = json.loads(contents["manifest.json"])
            data["schema"] = 99
            contents["manifest.json"] = json.dumps(data).encode()
        elif attack == "json_duplicate":
            contents["manifest.json"] = b'{"schema":1,"schema":1}'
        elif attack == "huge":
            contents["manifest.json"] = b"x" * (1024 * 1024)
        elif attack not in {"duplicate", "symlink"}:
            name = {
                "extra": "extra",
                "traversal": "../escape",
                "absolute": "/escape",
                "backslash": "a\\b",
                "colon": "C:/evil",
            }[attack]
            contents[name] = b"evil"

    rewrite(archive, bad, change)
    if attack in {"duplicate", "symlink"}:
        with zipfile.ZipFile(bad, "a") as output:
            if attack == "duplicate":
                with pytest.warns(UserWarning):
                    output.writestr("manifest.json", "{}")
            else:
                info = zipfile.ZipInfo("evil")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                output.writestr(info, "../escape")
    with pytest.raises(DomainError):
        target.inspect(str(bad))
    with pytest.raises(DomainError):
        target.import_bundle(str(bad))
    assert not target.repository.list_entities(Part)
    assert not target.publications.list_publications()
    assert not target.store.root.exists()


def test_failure_after_install_rolls_back_catalogue_and_version(
    publications: tuple[Publications, Collection],
    target: LocalBundles,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, archive, publication = exported(publications, tmp_path)
    original = target.publications.verify

    def fail(record: Publication) -> None:
        original(record)
        raise DomainError("Simulated final failure")

    monkeypatch.setattr(target.publications, "verify", fail)
    with pytest.raises(DomainError, match="Simulated"):
        target.import_bundle(str(archive))
    assert not target.repository.list_entities(Part)
    assert not target.repository.list_entities(Asset)
    assert not target.publications._folder(publication.collection_id, 7).exists()
    # Content-addressed orphan blobs are harmless; a retry reuses verified bytes.
    monkeypatch.setattr(target.publications, "verify", original)
    target.import_bundle(str(archive))


def test_sql_commit_failure_rolls_back_history(
    publications: tuple[Publications, Collection],
    target: LocalBundles,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import event

    _, archive, publication = exported(publications, tmp_path)

    def fail_commit(connection: Connection) -> None:
        raise OperationalError("COMMIT", {}, Exception("disk"))

    event.listen(target.repository.engine, "commit", fail_commit)
    try:
        with pytest.raises(DomainError, match="annulé"):
            target.import_bundle(str(archive))
    finally:
        event.remove(target.repository.engine, "commit", fail_commit)
    assert not target.repository.list_entities(Part)
    assert not target.publications._folder(publication.collection_id, 7).exists()


def test_export_no_overwrite_and_missing_dependencies(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> None:
    transport, archive, publication = exported(publications, tmp_path)
    original = archive.read_bytes()
    with pytest.raises(DomainError, match="existante"):
        transport.export(publication, str(archive))
    assert archive.read_bytes() == original
    path = next((transport.publications._folder(publication.collection_id, 7) / "inputs").iterdir())
    path.unlink()
    with pytest.raises(DomainError):
        transport.export(publication, str(tmp_path / "broken.kiparts"))
    assert not (tmp_path / "broken.kiparts").exists()


def test_official_inherited_symbol_becomes_managed_without_changing_hash(
    target: LocalBundles, tmp_path: Path, engine: Engine
) -> None:
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.application.validation import LocalValidation
    from kipartmanager.domain.entities import AssetOrigin, AssetType
    from kipartmanager.domain.kicad import LibraryRoots
    from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
    from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
    from tests.test_publisher import local_probe
    from tests.test_validation import SYMBOL, setup_case

    validation, resolver, part, _, collection, _ = setup_case(tmp_path, engine)
    root = tmp_path / "official"
    for name in ("symbols", "footprints", "models"):
        (root / name).mkdir(parents=True)
    symbol = root / "symbols/Device.kicad_sym"
    symbol.write_text(
        SYMBOL[:-1] + '(symbol "Derived" (extends "R") (property "Value" "Derived" (at 0 0 0) '
        "(effects (font (size 1 1))))))"
    )
    index = LocalKiCadIndex(tmp_path / "index")
    index.configure(
        LibraryRoots(*(str(root / name) for name in ("symbols", "footprints", "models")))
    )
    index.rebuild(index.configuration())
    resolver.libraries = KiCadLibraries(index)
    candidate = next(
        c
        for c in resolver.search(part, AssetType.SYMBOL, "Derived").candidates
        if c.choice.reference
    )
    resolver.select(part, candidate, expected=resolver.choices(part)[0], replace_existing=True)
    local_probe(validation).index = index
    validation.validate(collection)
    builder = LocalLibraryBuilder(local_probe(validation).store, index, tmp_path / "source-data")
    service = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "history", builder),
    )
    publication = service.publish(collection, 1)
    archive = tmp_path / "official.kiparts"
    assert isinstance(validation.catalogue.repository, SqliteCatalogue)
    assert isinstance(service.store, LocalPublications)
    LocalBundles(validation.catalogue.repository, service.store).export(publication, str(archive))
    shutil.rmtree(root)
    target.import_bundle(str(archive))
    official = next(
        a for a in target.repository.list_entities(Asset) if a.origin is AssetOrigin.KICAD_OFFICIAL
    )
    assert official.file is not None and candidate.choice.reference is not None
    assert official.file.sha256 == candidate.choice.reference.sha256
    assert official.file.symbol_name == "Derived"
    assert official.source == candidate.choice.reference.key
    assert target.import_bundle(str(archive)).can_import
    assert target.store._path(official.file).read_bytes().decode().find('extends "R"') > 0
    # Current validation and a new publication work entirely against managed copies.
    from kipartmanager.application.catalogue import Catalogue

    catalogue = Catalogue(target.repository, target.store)
    probe = LocalResourceProbe(target.store, target.publications.builder.index)
    current = LocalValidation(catalogue, probe, SqliteValidationReports(target.repository.engine))
    imported_collection = catalogue.require(Collection, publication.collection_id)
    assert current.qualification(imported_collection).report is None
    assert current.validate(imported_collection).eligible
    new = Publications(
        LocalPublisher(catalogue, current, target.publications.builder), target.publications
    )
    newer = new.publish(imported_collection, 2)
    new.verify(newer)
    # M7 dependencies keep the entry selector across further transfers.
    again = tmp_path / "official-again.kiparts"
    target.export(newer, str(again))
    assert target.inspect(str(again)).can_import


def test_import_rechecks_conflict_after_preview(
    publications: tuple[Publications, Collection], target: LocalBundles, tmp_path: Path
) -> None:
    _, archive, publication = exported(publications, tmp_path)
    assert target.inspect(str(archive)).can_import
    target.repository.save(Collection(id=publication.collection_id, name="Local edits"))
    with pytest.raises(DomainError, match="conflits"):
        target.import_bundle(str(archive))
    assert not target.repository.list_entities(Asset)
    assert not target.publications.list_publications()


def test_archive_limits_checked_before_decompression(
    publications: tuple[Publications, Collection],
    target: LocalBundles,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kipartmanager.infrastructure.bundles as module

    _, archive, _ = exported(publications, tmp_path)
    monkeypatch.setattr(module, "MAX_BYTES", 2)
    with pytest.raises(DomainError, match="volumineuse"):
        target.inspect(str(archive))
    monkeypatch.setattr(module, "MAX_BYTES", 1024 * 1024 * 1024)
    monkeypatch.setattr(module, "MAX_JSON", 2)
    with pytest.raises(DomainError, match="volumineux"):
        target.inspect(str(archive))


def test_shared_package_model_and_pdf_are_transferred_once(
    tmp_path: Path, engine: Engine, target: LocalBundles
) -> None:
    from kipartmanager.application.asset_imports import AssetImports
    from kipartmanager.domain.entities import AssetType
    from tests.test_validation import FOOTPRINT

    footprint = (
        FOOTPRINT[:-1]
        + '(model "R.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))'
    )
    validation, resolver, part, package, collection, _ = setup_case(
        tmp_path, engine, footprint=footprint
    )
    store = local_probe(validation).store
    imports = AssetImports(validation.catalogue, store)
    for name, content, role, owner in [
        ("R.step", b"ISO-10303-21; END-ISO-10303-21;", AssetType.MODEL_3D, package),
        ("sheet.pdf", b"%PDF-1.4 fixture", AssetType.DATASHEET, part),
    ]:
        path = tmp_path / name
        path.write_bytes(content)
        asset = imports.import_file(
            str(path), name=name, source_reference="https://example.org/resources/" + name
        )
        assert isinstance(owner, (Part, Package))
        resolver.select(
            owner,
            next(
                c
                for c in resolver.search(owner, role, name).candidates
                if c.choice.asset_id == asset.id
            ),
        )
    second = Part(name="Second", package_id=package.id)
    validation.catalogue.save(second)
    resolver.select(second, resolver.search(second, AssetType.SYMBOL, "R").candidates[0])
    collection = replace(collection, part_ids=(part.id, second.id))
    validation.catalogue.save(collection)
    validation.validate(collection)
    builder = LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data")
    history = LocalPublications(tmp_path / "history", builder)
    service = Publications(LocalPublisher(validation.catalogue, validation, builder), history)
    assert isinstance(validation.catalogue.repository, SqliteCatalogue)
    transport = LocalBundles(validation.catalogue.repository, history)
    validation.validate(collection, accept_warnings=True)
    publication = service.publish(collection, 1)
    archive = tmp_path / "complete.kiparts"
    transport.export(publication, str(archive))
    target.import_bundle(str(archive))
    assert len(target.repository.list_entities(Part)) == 2
    assert len(target.repository.list_entities(Package)) == 1
    assert len(target.repository.list_entities(Asset)) == 4
    model = next(
        a for a in target.repository.list_entities(Asset) if a.asset_type is AssetType.MODEL_3D
    )
    assert model.source == "https://example.org/resources/R.step"
    result = target.publications.rebuild(publication, str(tmp_path / "complete-output"))
    assert result.symbols == 2 and result.footprints == 1
    assert len(list(Path(result.destination).glob("*.3dshapes/*.step"))) == 1
    assert len(list(Path(result.destination).glob("datasheets/*.pdf"))) == 1
