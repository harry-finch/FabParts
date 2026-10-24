"""Qualified standalone builds, stable identities, resolved links and preservation."""

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.build import BuildPlan
from kipartmanager.domain.entities import Asset, AssetType, Collection, DomainError, Part
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_parser import parse
from kipartmanager.infrastructure.kicad_writer import serialize
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from tests.test_validation import FOOTPRINT, SYMBOL, setup_case


def local_probe(validation: LocalValidation) -> LocalResourceProbe:
    assert isinstance(validation.probe, LocalResourceProbe)
    return validation.probe


@pytest.fixture
def case(tmp_path: Path, engine: Engine) -> tuple[LocalPublisher, Collection]:
    validation, _, _, _, collection, _ = setup_case(tmp_path, engine)
    store = local_probe(validation).store
    builder = LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data")
    return LocalPublisher(validation.catalogue, validation, builder), collection


def tree_files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_collection_gate_before_files(
    case: tuple[LocalPublisher, Collection], tmp_path: Path
) -> None:
    publisher, collection = case
    target = tmp_path / "output"
    with pytest.raises(DomainError, match="non publiable"):
        publisher.build(collection, str(target))
    assert not target.exists()
    publisher.validation.validate(collection)
    publisher.catalogue.save(replace(collection, part_ids=()))
    with pytest.raises(DomainError):
        publisher.build(collection, str(target))
    publisher.validation.validate(collection)
    with pytest.raises(DomainError):
        publisher.build(collection, str(target))
    assert not target.exists()


def test_rebuild_identical_and_sources_preserved(
    case: tuple[LocalPublisher, Collection], tmp_path: Path
) -> None:
    publisher, collection = case
    assets = publisher.catalogue.list_entities(Asset)
    source_contents = tree_files(tmp_path / "assets")
    publisher.validation.validate(collection)
    first = publisher.build(collection, str(tmp_path / "first"))
    second = publisher.build(collection, str(tmp_path / "second"))
    assert first.files == second.files
    assert tree_files(Path(first.destination)) == tree_files(Path(second.destination))
    assert tree_files(tmp_path / "assets") == source_contents
    assert publisher.catalogue.list_entities(Asset) == assets
    assert publisher.validation.qualification(collection).eligible
    assert (first.symbols, first.footprints) == (1, 1)
    assert set(first.files) == {
        f"{first.library}.kicad_sym",
        f"{first.library}.pretty/F_{publisher.plan(collection).parts[0].package_id.hex}.kicad_mod",
        "UTILISATION.txt",
        "SOURCES.txt",
        "fp-lib-table",
        "sym-lib-table",
    }
    assert not (Path(first.destination) / "BUILDING").exists()
    root = parse((Path(first.destination) / f"{first.library}.kicad_sym").read_text())
    node = root.children_named("symbol")[0]
    fp = next(p for p in node.children_named("property") if p.atoms[1] == "Footprint")
    assert fp.atoms[2].startswith(first.library + ":F_")


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "data", "store"])
def test_destination_protection(
    case: tuple[LocalPublisher, Collection], tmp_path: Path, kind: str
) -> None:
    publisher, collection = case
    publisher.validation.validate(collection)
    target = tmp_path / "exists"
    if kind == "directory":
        target.mkdir()
    elif kind == "file":
        target.write_bytes(b"keep")
    elif kind == "symlink":
        target.symlink_to(tmp_path / "absent")
    elif kind == "data":
        target = tmp_path / "data" / "out"
    else:
        target = tmp_path / "assets" / "out"
    with pytest.raises(DomainError):
        publisher.build(collection, str(target))
    if kind == "file":
        assert target.read_bytes() == b"keep"
    if kind == "directory":
        assert list(target.iterdir()) == []


def test_shared_package_and_separate_seed_collections(
    case: tuple[LocalPublisher, Collection], tmp_path: Path
) -> None:
    publisher, collection = case
    publisher.catalogue.initialize_defaults()
    first_part = publisher.catalogue.require(Part, collection.part_ids[0])
    second_part = Part(name="same name", package_id=first_part.package_id)
    publisher.catalogue.save(second_part)
    repo = publisher.catalogue.repository
    choice = repo.choices(first_part)[0]
    assert isinstance(repo, SqliteCatalogue)
    repo.choose(second_part, choice, None)
    collections = [
        c
        for c in publisher.catalogue.list_entities(Collection)
        if c.name in {"LabParts", "PersonalParts"}
    ]
    outputs = []
    for item in collections:
        current = replace(item, part_ids=(first_part.id, second_part.id))
        publisher.catalogue.save(current)
        publisher.validation.validate(current)
        result = publisher.build(current, str(tmp_path / current.name))
        assert (result.symbols, result.footprints) == (2, 1)
        assert (
            len(
                parse(
                    (Path(result.destination) / f"{result.library}.kicad_sym").read_text()
                ).children_named("symbol")
            )
            == 2
        )
        outputs.append(result)
    assert outputs[0].library != outputs[1].library
    assert publisher.catalogue.require(Part, first_part.id).name == "R"


@pytest.mark.parametrize("moment", ["prepare", "install"])
def test_change_during_build_blocks_and_cleans(
    case: tuple[LocalPublisher, Collection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    moment: str,
) -> None:
    publisher, collection = case
    publisher.validation.validate(collection)
    builder = publisher.builder
    original = publisher.plan
    calls = 0

    def changed(subject: Collection) -> BuildPlan:
        nonlocal calls
        calls += 1
        if calls == (2 if moment == "prepare" else 3):
            current = publisher.catalogue.require(Part, collection.part_ids[0])
            publisher.catalogue.save(replace(current, description="changed"))
        return original(subject)

    monkeypatch.setattr(publisher, "plan", changed)
    with pytest.raises(DomainError):
        publisher.build(collection, str(tmp_path / "output"))
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".kipart-build-*"))
    assert builder is publisher.builder


def test_semantic_serialization_preserves_quotes_and_atom_order() -> None:
    text = '(root "123" token (effects (font (size 1 1)) hide) "a\\\\b\\"c\\nd")'
    node = parse(text)
    rendered = serialize(node)
    assert parse(rendered) == node
    assert "(font" in rendered and rendered.index("(font") < rendered.index(" hide")
    assert '"123"' in rendered


@pytest.mark.parametrize("link", ["missing", "different", "multiple", "no_transform"])
def test_unresolved_model_links_are_build_errors(tmp_path: Path, engine: Engine, link: str) -> None:
    model = '(model "R.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))'
    fp = FOOTPRINT if link == "no_transform" else FOOTPRINT[:-1] + model + ")"
    if link == "different":
        fp = fp.replace("R.step", "other.step")
    if link == "multiple":
        fp = fp[:-1] + model.replace("R.step", "other.step") + ")"
    validation, resolver, _, package, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    store = local_probe(validation).store
    if link != "missing":
        source = tmp_path / "R.step"
        source.write_text("ISO-10303-21; END-ISO-10303-21;")
        AssetImports(validation.catalogue, store).import_file(str(source), name="model")
        resolver.select(
            package, resolver.search(package, AssetType.MODEL_3D, "model").candidates[0]
        )
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    publisher = LocalPublisher(
        validation.catalogue,
        validation,
        LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"),
    )
    with pytest.raises(DomainError):
        publisher.build(collection, str(tmp_path / "output"))
    assert not (tmp_path / "output").exists()


def test_model_and_datasheet_copied_with_transforms(tmp_path: Path, engine: Engine) -> None:
    fp = (
        FOOTPRINT[:-1]
        + '(model "R.step" (offset (xyz 1 2 3)) (scale (xyz 2 2 2)) (rotate (xyz 0 0 90))))'
    )
    validation, resolver, part, package, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    store = local_probe(validation).store
    for extension, owner, role in (
        (".step", package, AssetType.MODEL_3D),
        (".pdf", part, AssetType.DATASHEET),
    ):
        source = tmp_path / ("R" + extension)
        source.write_bytes(
            b"ISO-10303-21; END-ISO-10303-21;" if extension == ".step" else b"opaque PDF"
        )
        AssetImports(validation.catalogue, store).import_file(str(source), name=extension)
        resolver.select(owner, resolver.search(owner, role, extension).candidates[0])
    validation.validate(collection)
    publisher = LocalPublisher(
        validation.catalogue,
        validation,
        LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"),
    )
    with pytest.raises(DomainError):
        publisher.build(collection, str(tmp_path / "blocked"))
    validation.validate(collection, accept_warnings=True)
    result = publisher.build(collection, str(tmp_path / "output"))
    output = Path(result.destination)
    fp_tree = parse(next(output.glob("*.pretty/*.kicad_mod")).read_text())
    model = fp_tree.children_named("model")[0]
    assert model.children_named("offset")[0].value("xyz") == "1"
    assert model.children_named("scale")[0].value("xyz") == "2"
    assert model.atoms[1].startswith("${KIPRJMOD}/")
    assert (
        output / model.atoms[1].removeprefix("${KIPRJMOD}/")
    ).read_bytes() == b"ISO-10303-21; END-ISO-10303-21;"
    assert len(list(output.glob("datasheets/*.pdf"))) == 1
    assert all("/Users/" not in p.read_text() for p in output.rglob("*") if p.is_file())


def test_inherited_symbol_closure_retained(tmp_path: Path, engine: Engine) -> None:
    validation, resolver, part, _, collection, assets = setup_case(tmp_path, engine)
    # Official references identify an entry in a multi-symbol file.
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.domain.kicad import LibraryRoots

    index = LocalKiCadIndex(tmp_path / "index-data")
    roots = tmp_path / "official"
    for folder in ("symbols", "footprints", "models"):
        (roots / folder).mkdir(parents=True)
    content = (
        SYMBOL[:-1] + '(symbol "Derived" (extends "R") (property "Value" "Derived" (at 0 0 0) '
        "(effects (font (size 1 1))))))"
    )
    (roots / "symbols/Device.kicad_sym").write_text(content)
    index.configure(
        LibraryRoots(str(roots / "symbols"), str(roots / "footprints"), str(roots / "models"))
    )
    index.rebuild(index.configuration())
    resolver.libraries = KiCadLibraries(index)
    resolver.select(
        part,
        next(
            c
            for c in resolver.search(part, AssetType.SYMBOL, "Derived").candidates
            if c.choice.reference and c.choice.reference.name == "Derived"
        ),
        expected=resolver.choices(part)[0],
        replace_existing=True,
    )
    local_probe(validation).index = index
    validation.validate(collection)
    store = local_probe(validation).store
    publisher = LocalPublisher(
        validation.catalogue, validation, LocalLibraryBuilder(store, index, tmp_path / "data")
    )
    result = publisher.build(collection, str(tmp_path / "output"))
    root = parse((Path(result.destination) / f"{result.library}.kicad_sym").read_text())
    entries = root.children_named("symbol")
    assert len(entries) == 2
    assert entries[1].value("extends") == entries[0].atoms[1]
    assert entries[0].children_named("symbol")[0].atoms[1] == entries[0].atoms[1] + "_1_1"
    assert (roots / "symbols/Device.kicad_sym").read_text() == content
    assert publisher.catalogue.require(Asset, assets[0].id).file == assets[0].file


def test_link_failure_cleans_only_owned_outputs(
    case: tuple[LocalPublisher, Collection], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    publisher, collection = case
    publisher.validation.validate(collection)
    original = os.link
    calls = 0
    target = tmp_path / "output"

    def failed(source: str, destination: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            (target / "external.txt").write_text("keep")
            raise OSError("simulated write failure")
        original(source, destination)

    monkeypatch.setattr(os, "link", failed)
    with pytest.raises(DomainError, match="Construction impossible"):
        publisher.build(collection, str(target))
    assert tree_files(target) == {"external.txt": b"keep"}
    assert not list(tmp_path.glob(".kipart-build-*"))


def test_existing_destination_created_during_staging_is_preserved(
    case: tuple[LocalPublisher, Collection], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher, collection = case
    publisher.validation.validate(collection)
    target = tmp_path / "output"
    original = publisher.plan
    calls = 0

    def raced(subject: Collection) -> BuildPlan:
        nonlocal calls
        calls += 1
        if calls == 2:
            target.mkdir()
            (target / "keep").write_bytes(b"keep")
        return original(subject)

    monkeypatch.setattr(publisher, "plan", raced)
    with pytest.raises(DomainError):
        publisher.build(collection, str(target))
    assert tree_files(target) == {"keep": b"keep"}


def test_corrupt_resource_after_plan_does_not_produce_output(
    case: tuple[LocalPublisher, Collection], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher, collection = case
    publisher.validation.validate(collection)
    original = publisher.plan

    def changed(subject: Collection) -> BuildPlan:
        plan = original(subject)
        asset = publisher.catalogue.list_entities(Asset)[0]
        assert asset.file is not None
        path = tmp_path / "assets" / asset.file.relative_key
        path.write_bytes(b"corrupted")
        return plan

    monkeypatch.setattr(publisher, "plan", changed)
    with pytest.raises(DomainError):
        publisher.build(collection, str(tmp_path / "output"))
    assert not (tmp_path / "output").exists()


def test_external_simulation_dependency_is_not_silently_copied(
    tmp_path: Path, engine: Engine
) -> None:
    symbol = SYMBOL.replace(
        '(symbol "R"', '(symbol "R" (property "Sim.Library" "/some/local/model.lib")', 1
    )
    validation, _, _, _, collection, _ = setup_case(tmp_path, engine, symbol=symbol)
    validation.validate(collection)
    store = local_probe(validation).store
    publisher = LocalPublisher(
        validation.catalogue,
        validation,
        LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"),
    )
    with pytest.raises(DomainError, match="simulation"):
        publisher.build(collection, str(tmp_path / "output"))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "extension,content",
    [
        (".wrl", '#VRML V2.0 utf8\nInline { url "other.wrl" }'),
        (".step", "ISO-10303-21; #1=EXTERNAL_SOURCE(); END-ISO-10303-21;"),
    ],
)
def test_external_3d_dependency_blocks_build(
    tmp_path: Path, engine: Engine, extension: str, content: str
) -> None:
    fp = (
        FOOTPRINT[:-1]
        + f'(model "R{extension}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))'
    )
    validation, resolver, _, package, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    store = local_probe(validation).store
    source = tmp_path / ("R" + extension)
    source.write_text(content)
    AssetImports(validation.catalogue, store).import_file(str(source), name="model")
    resolver.select(package, resolver.search(package, AssetType.MODEL_3D, "model").candidates[0])
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    publisher = LocalPublisher(
        validation.catalogue,
        validation,
        LocalLibraryBuilder(store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"),
    )
    with pytest.raises(DomainError, match="Dépendance externe"):
        publisher.build(collection, str(tmp_path / "output"))
    assert not (tmp_path / "output").exists()


def test_reference_without_index_cache_can_build_and_protects_official_root(
    tmp_path: Path, engine: Engine
) -> None:
    validation, resolver, part, _, collection, _ = setup_case(tmp_path, engine)
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.domain.kicad import LibraryRoots

    index = LocalKiCadIndex(tmp_path / "index-data")
    root = tmp_path / "official"
    for folder in ("symbols", "footprints", "models"):
        (root / folder).mkdir(parents=True)
    source = root / "symbols/Device.kicad_sym"
    source.write_text(SYMBOL)
    index.configure(LibraryRoots(*(str(root / f) for f in ("symbols", "footprints", "models"))))
    index.rebuild(index.configuration())
    resolver.libraries = KiCadLibraries(index)
    resolver.select(
        part,
        next(
            c
            for c in resolver.search(part, AssetType.SYMBOL, "Device:R").candidates
            if c.choice.reference
        ),
        expected=resolver.choices(part)[0],
        replace_existing=True,
    )
    local_probe(validation).index = index
    validation.validate(collection)
    index.cache.unlink()
    publisher = LocalPublisher(
        validation.catalogue,
        validation,
        LocalLibraryBuilder(local_probe(validation).store, index, tmp_path / "data"),
    )
    with pytest.raises(DomainError, match="hors des données"):
        publisher.build(collection, str(root / "symbols/out"))
    assert source.read_text() == SYMBOL
    assert publisher.build(collection, str(tmp_path / "output")).symbols == 1
