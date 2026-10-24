"""Immutable history, retained official dependencies and atomic commit failures."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine

from kipartmanager.application.publications import Publications
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.domain.build import BuildPlan
from kipartmanager.domain.entities import Asset, Collection, DomainError, Package, Part
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
    publisher = LocalPublisher(validation.catalogue, validation, builder)
    validation.validate(collection)
    return Publications(
        publisher, LocalPublications(tmp_path / "data/publications", builder)
    ), collection


def folder(service: Publications, collection: Collection, version: int) -> Path:
    assert isinstance(service.store, LocalPublications)
    return service.store.root / str(collection.id) / f"v{version:06d}"


def test_two_versions_frozen_reconstruction(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> None:
    service, collection = publications
    first = service.publish(collection, 1)
    saved = tree_files(folder(service, collection, 1))
    catalogue = service.publisher.catalogue
    part = catalogue.require(Part, collection.part_ids[0])
    catalogue.save(replace(part, name="Changed part"))
    service.publisher.validation.validate(collection)
    second = service.publish(collection, 2)
    assert first != second
    assert tree_files(folder(service, collection, 1)) == saved
    assert service.list_publications(collection.id) == (first, second)
    service.verify(first)
    rebuilt = service.rebuild(first, str(tmp_path / "rebuilt"))
    assert tree_files(Path(rebuilt.destination)) == {
        name.removeprefix("artifacts/"): content
        for name, content in saved.items()
        if name.startswith("artifacts/")
    }
    assert (
        b"Changed part"
        not in (Path(rebuilt.destination) / f"{rebuilt.library}.kicad_sym").read_bytes()
    )
    # Current managed bytes and database data no longer participate in reconstruction.
    for asset in catalogue.list_entities(Asset):
        if asset.file:
            local_probe(service.publisher.validation).store._path(asset.file).unlink(
                missing_ok=True
            )
    catalogue.save(replace(collection, part_ids=()))
    service.rebuild(first, str(tmp_path / "without-current-sources"))
    service.verify(first)
    assert tree_files(folder(service, collection, 1)) == saved


def test_no_overwrite_and_gate(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> None:
    service, collection = publications
    first = service.publish(collection, 1)
    saved = tree_files(folder(service, collection, 1))
    with pytest.raises(DomainError, match="immuable"):
        service.publish(collection, 1)
    assert tree_files(folder(service, collection, 1)) == saved
    target = tmp_path / "exists"
    target.mkdir()
    with pytest.raises(DomainError, match="existante"):
        service.rebuild(first, str(target))
    service.publisher.catalogue.save(replace(collection, part_ids=()))
    with pytest.raises(DomainError):
        service.publish(collection, 2)
    assert not folder(service, collection, 2).exists()


@pytest.mark.parametrize("version", [0, -1, True, 1000000])
def test_invalid_version(publications: tuple[Publications, Collection], version: int) -> None:
    service, collection = publications
    with pytest.raises(DomainError, match="Version"):
        service.publish(collection, version)
    assert service.list_publications() == ()


def test_partial_directory_ignored(publications: tuple[Publications, Collection]) -> None:
    service, collection = publications
    target = folder(service, collection, 1)
    target.mkdir(parents=True)
    (target / "manifest.json").write_text("{}")
    assert service.list_publications() == ()
    with pytest.raises(DomainError, match="immuable"):
        service.publish(collection, 1)


@pytest.mark.parametrize("file", ["manifest.json", "COMMIT", "input", "artifact"])
def test_corruption_detected(
    publications: tuple[Publications, Collection], file: str, tmp_path: Path
) -> None:
    service, collection = publications
    published = service.publish(collection, 1)
    root = folder(service, collection, 1)
    if file == "input":
        path = next((root / "inputs").iterdir())
    elif file == "artifact":
        path = next((root / "artifacts").glob("*.kicad_sym"))
    else:
        path = root / file
    path.write_bytes(b"corrupt")
    with pytest.raises(DomainError):
        service.verify(published)
    if file != "artifact":
        with pytest.raises(DomainError):
            service.rebuild(published, str(tmp_path / "failed"))
        assert not (tmp_path / "failed").exists()
    else:
        # Artifacts are not primary storage; intact retained inputs can regenerate them.
        service.rebuild(published, str(tmp_path / "recovered"))


def test_late_failure_not_committed(
    publications: tuple[Publications, Collection], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, collection = publications
    original = service.publisher.plan
    calls = 0

    def change_late(subject: Collection) -> BuildPlan:
        nonlocal calls
        calls += 1
        if calls == 3:
            service.publisher.catalogue.save(replace(collection, part_ids=()))
        return original(subject)

    monkeypatch.setattr(service.publisher, "plan", change_late)
    with pytest.raises(DomainError):
        service.publish(collection, 1)
    assert service.list_publications() == ()
    assert not folder(service, collection, 1).exists()


def test_portable_manifest(publications: tuple[Publications, Collection], tmp_path: Path) -> None:
    service, collection = publications
    published = service.publish(collection, 1)
    content = (folder(service, collection, 1) / "manifest.json").read_text()
    assert str(tmp_path) not in content
    data = json.loads(content)
    assert data["version"] == 1
    assert data["plan"]["parts"][0]["package_id"]
    assert data["validation"]["fingerprint"] == published.fingerprint
    assert len(data["dependencies"]) == 2
    assert all(d["sha256"] and d["origin"] == "USER_PROVIDED" for d in data["dependencies"])


def test_official_inheritance_survives_update_and_removal(tmp_path: Path, engine: Engine) -> None:
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.domain.entities import AssetType
    from kipartmanager.domain.kicad import LibraryRoots
    from kipartmanager.infrastructure.kicad_parser import parse
    from tests.test_validation import SYMBOL

    validation, resolver, part, _, collection, assets = setup_case(tmp_path, engine)
    index = LocalKiCadIndex(tmp_path / "index-data")
    root = tmp_path / "official"
    for name in ("symbols", "footprints", "models"):
        (root / name).mkdir(parents=True)
    source = root / "symbols/Device.kicad_sym"
    content = (
        SYMBOL[:-1] + '(symbol "Derived" (extends "R") (property "Value" "Derived" (at 0 0 0) '
        "(effects (font (size 1 1))))))"
    )
    source.write_text(content)
    index.configure(
        LibraryRoots(*(str(root / name) for name in ("symbols", "footprints", "models")))
    )
    index.rebuild(index.configuration())
    resolver.libraries = KiCadLibraries(index)
    resolver.select(
        part,
        next(
            c
            for c in resolver.search(part, AssetType.SYMBOL, "Derived").candidates
            if c.choice.reference
        ),
        expected=resolver.choices(part)[0],
        replace_existing=True,
    )
    local_probe(validation).index = index
    validation.validate(collection)
    builder = LocalLibraryBuilder(local_probe(validation).store, index, tmp_path / "data")
    service = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "data/publications", builder),
    )
    published = service.publish(collection, 1)
    assert source.read_text() == content
    assert validation.catalogue.require(Asset, assets[0].id) == assets[0]
    source.write_text("changed official installation")
    with pytest.raises(DomainError):
        service.publish(collection, 2)
    source.unlink()
    result = service.rebuild(published, str(tmp_path / "rebuilt"))
    entries = parse(
        (Path(result.destination) / f"{result.library}.kicad_sym").read_text()
    ).children_named("symbol")
    assert len(entries) == 2
    assert entries[1].value("extends") == entries[0].atoms[1]
    manifest = json.loads((folder(service, collection, 1) / "manifest.json").read_text())
    assert any(d["origin"] == "KICAD_OFFICIAL" for d in manifest["dependencies"])
    assert str(root) not in json.dumps(manifest)
    service.verify(published)


def test_commit_io_failure_cleans_and_preserves_existing_history(
    publications: tuple[Publications, Collection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    service, collection = publications
    first = service.publish(collection, 1)
    saved = tree_files(folder(service, collection, 1))
    original = os.link

    def fail_commit(source: Path, target: Path) -> None:
        if source.name == "COMMIT":
            raise OSError("Commit injection")
        original(source, target)

    monkeypatch.setattr(os, "link", fail_commit)
    with pytest.raises(DomainError):
        service.publish(collection, 2)
    assert service.list_publications() == (first,)
    assert tree_files(folder(service, collection, 1)) == saved
    assert not folder(service, collection, 2).exists()
    assert not list(folder(service, collection, 1).parent.glob(".pending-*"))


def test_rebuild_never_reads_current_catalogue(
    publications: tuple[Publications, Collection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, collection = publications
    published = service.publish(collection, 1)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Current catalogue or qualification read during rebuild")

    monkeypatch.setattr(service.publisher, "plan", forbidden)
    monkeypatch.setattr(service.publisher.catalogue, "require", forbidden)
    service.rebuild(published, str(tmp_path / "historical"))


def test_model_datasheet_and_shared_package_retained(tmp_path: Path, engine: Engine) -> None:
    from kipartmanager.application.asset_imports import AssetImports
    from kipartmanager.domain.entities import AssetType
    from tests.test_validation import FOOTPRINT

    fp = (
        FOOTPRINT[:-1]
        + '(model "R.step" (offset (xyz 1 2 3)) (scale (xyz 2 2 2)) (rotate (xyz 0 0 90))))'
    )
    validation, resolver, part, package, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    store = local_probe(validation).store
    imports = AssetImports(validation.catalogue, store)
    for filename, data, kind, owner in [
        ("R.step", b"ISO-10303-21; END-ISO-10303-21;", AssetType.MODEL_3D, package),
        ("sheet.pdf", b"opaque PDF", AssetType.DATASHEET, part),
    ]:
        assert isinstance(owner, (Part, Package))
        source = tmp_path / filename
        source.write_bytes(data)
        asset = imports.import_file(str(source), name=filename)
        resolver.select(
            owner,
            next(
                c
                for c in resolver.search(owner, kind, filename).candidates
                if c.choice.asset_id == asset.id
            ),
        )
    second = Part(name="Shared package", package_id=package.id)
    validation.catalogue.save(second)
    resolver.select(second, resolver.search(second, AssetType.SYMBOL, "R").candidates[0])
    collection = replace(collection, part_ids=(part.id, second.id))
    validation.catalogue.save(collection)
    validation.validate(collection)
    builder = LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data")
    service = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "data/publications", builder),
    )
    with pytest.raises(DomainError):
        service.publish(collection, 1)
    validation.validate(collection, accept_warnings=True)
    published = service.publish(collection, 1)
    saved = tree_files(folder(service, collection, 1) / "artifacts")
    for blob in store.root.rglob("*"):
        if blob.is_file():
            blob.unlink()
    result = service.rebuild(published, str(tmp_path / "rebuilt"))
    assert tree_files(Path(result.destination)) == saved
    assert result.symbols == 2 and result.footprints == 1
    assert len(list(Path(result.destination).glob("*.3dshapes/*.step"))) == 1
    assert len(list(Path(result.destination).glob("datasheets/*.pdf"))) == 1


def test_concurrent_same_version_has_one_winner(
    publications: tuple[Publications, Collection],
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    service, collection = publications

    def attempt() -> bool:
        try:
            service.publish(collection, 1)
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [False, True]
    history = service.list_publications()
    assert len(history) == 1
    service.verify(history[0])


def test_versions_are_scoped_by_collection(publications: tuple[Publications, Collection]) -> None:
    service, collection = publications
    other = Collection(name="Second collection", part_ids=collection.part_ids)
    service.publisher.catalogue.save(other)
    service.publisher.validation.validate(other)
    first = service.publish(collection, 1)
    second = service.publish(other, 1)
    assert first.collection_id != second.collection_id
    assert service.list_publications(collection.id) == (first,)
    assert service.list_publications(other.id) == (second,)
    assert len(service.list_publications()) == 2
    service.verify(first)
    service.verify(second)


def test_source_symlink_refused(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> None:
    service, collection = publications
    published = service.publish(collection, 1)
    source = next((folder(service, collection, 1) / "inputs").iterdir())
    outside = tmp_path / "foreign"
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(DomainError, match="symbolique"):
        service.rebuild(published, str(tmp_path / "no-output"))
    assert not (tmp_path / "no-output").exists()


def test_new_builder_bytes_refused(
    publications: tuple[Publications, Collection], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kipartmanager.infrastructure.publications import FrozenBuilder

    service, collection = publications
    published = service.publish(collection, 1)
    original = FrozenBuilder._construct

    def different(self: FrozenBuilder, plan: BuildPlan, staging: Path) -> tuple[int, int]:
        result = original(self, plan, staging)
        (staging / "UTILISATION.txt").write_text("Different future builder output")
        return result

    monkeypatch.setattr(FrozenBuilder, "_construct", different)
    with pytest.raises(DomainError, match="différente"):
        service.rebuild(published, str(tmp_path / "future"))
    assert not (tmp_path / "future").exists()
    service.verify(published)


def test_storage_root_blocked_is_explicit(publications: tuple[Publications, Collection]) -> None:
    service, _ = publications
    assert isinstance(service.store, LocalPublications)
    service.store.root.parent.mkdir(parents=True, exist_ok=True)
    service.store.root.write_text("foreign file")
    with pytest.raises(DomainError, match="inaccessible"):
        service.list_publications()


def test_never_publish_inside_official_root(publications: tuple[Publications, Collection]) -> None:
    from kipartmanager.domain.kicad import LibraryRoots

    service, collection = publications
    assert isinstance(service.store, LocalPublications)
    service.store.root.parent.mkdir(parents=True, exist_ok=True)
    service.store.builder.index = LocalKiCadIndex(service.store.root.parent.parent / "other-index")
    service.store.builder.index.configure(LibraryRoots(symbols=str(service.store.root.parent)))
    with pytest.raises(DomainError, match="bibliothèque source"):
        service.publish(collection, 1)
    assert not service.store.root.exists()
