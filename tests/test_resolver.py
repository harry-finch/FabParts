"""Priority, explicit selection, persistence and preservation of local resources."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import IntegrityError

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    ConflictError,
    DomainError,
    Package,
    Part,
)
from kipartmanager.domain.kicad import LibraryRoots
from kipartmanager.domain.resolution import CandidateTier, ResourceChoice
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.models import ChoiceRow


@pytest.fixture
def resolver_setup(
    tmp_path: Path, engine: Engine
) -> tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]]:
    repository = SqliteCatalogue(engine)
    store = LocalAssetStore(tmp_path / "data/assets")
    catalogue = Catalogue(repository, store)
    importer = AssetImports(catalogue, store)
    source = tmp_path / "R.kicad_sym"
    source.write_text('(kicad_symbol_lib (version 20251024) (generator fixture) (symbol "R"))')
    assets = tuple(
        importer.import_file(str(source), name="R", origin=origin, source_reference="fixture")
        for origin in (AssetOrigin.USER_PROVIDED, AssetOrigin.MANAGED_LIBRARY)
    )
    symbols = tmp_path / "official/symbols"
    symbols.mkdir(parents=True)
    (symbols / "Device.kicad_sym").write_bytes(source.read_bytes())
    index = LocalKiCadIndex(tmp_path / "data")
    index.configure(LibraryRoots(symbols=str(symbols)))
    index.rebuild(index.configuration())
    part = Part(name="R", asset_ids=(assets[0].id,))
    catalogue.save(part)
    resolver = LocalResolver(catalogue, repository, KiCadLibraries(index))
    return resolver, index, part, assets


def test_distinct_priority_and_no_automatic_choice(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, assets = resolver_setup
    result = resolver.search(part, AssetType.SYMBOL, "r")
    assert [c.tier for c in result.candidates] == [
        CandidateTier.USER,
        CandidateTier.MANAGED,
        CandidateTier.KICAD,
    ]
    assert len({c.choice.key for c in result.candidates}) == 3
    assert len({c.sha256 for c in result.candidates}) == 1
    assert resolver.choices(part) == ()
    assert resolver.catalogue.require(Part, part.id) == part
    assert resolver.catalogue.list_entities(Asset) == sorted(
        assets, key=lambda a: (a.name, str(a.id))
    )


def test_explicit_replacement_preserves_user_and_membership(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, assets = resolver_setup
    candidates = resolver.search(part, AssetType.SYMBOL, "R").candidates
    resolver.select(part, candidates[0])
    before = resolver.catalogue.require(Asset, assets[0].id)
    with pytest.raises(DomainError, match="Confirmer"):
        resolver.select(part, candidates[2], expected=candidates[0].choice)
    assert resolver.choices(part) == (candidates[0].choice,)
    resolver.select(part, candidates[2], expected=candidates[0].choice, replace_existing=True)
    assert resolver.choices(part) == (candidates[2].choice,)
    assert resolver.catalogue.require(Part, part.id).asset_ids == part.asset_ids
    assert resolver.catalogue.require(Asset, assets[0].id) == before
    assert len(resolver.catalogue.list_entities(Asset)) == 2
    resolver.select(part, candidates[1], expected=candidates[2].choice, replace_existing=True)
    assert set(resolver.catalogue.require(Part, part.id).asset_ids) == {a.id for a in assets}


def test_stale_dialog_and_repository_compare_expected(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, _ = resolver_setup
    first, second, _ = resolver.search(part, AssetType.SYMBOL, "R").candidates
    resolver.select(part, first)
    with pytest.raises(DomainError, match="changé"):
        resolver.select(part, second, replace_existing=True)
    with pytest.raises(ConflictError, match="changé"):
        resolver.repository.choose(part, second.choice, None)
    assert resolver.choices(part) == (first.choice,)


def test_selection_reopens_without_index(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, index, part, _ = resolver_setup
    official = resolver.search(part, AssetType.SYMBOL, "R").candidates[-1]
    resolver.select(part, official)
    index.cache.unlink()
    reopened = LocalResolver(
        Catalogue(resolver.catalogue.repository, resolver.catalogue.store), resolver.repository
    )
    assert reopened.choices(part) == (official.choice,)
    assert reopened.search(part, AssetType.SYMBOL, "R").notices
    assert len(reopened.search(part, AssetType.SYMBOL, "R").candidates) == 2


def test_unavailable_metadata_and_corrupt_managed_file(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, assets = resolver_setup
    metadata = Asset(name="R", asset_type=AssetType.SYMBOL, origin=AssetOrigin.USER_PROVIDED)
    resolver.catalogue.save(metadata)
    candidate = next(
        c
        for c in resolver.search(part, AssetType.SYMBOL, "R").candidates
        if c.choice.asset_id == metadata.id
    )
    assert candidate.unavailable
    with pytest.raises(DomainError, match="sans fichier"):
        resolver.select(part, candidate)
    selected = next(
        c
        for c in resolver.search(part, AssetType.SYMBOL, "R").candidates
        if c.choice.asset_id == assets[0].id
    )
    assert assets[0].file is not None
    store = resolver.catalogue.store
    assert isinstance(store, LocalAssetStore)
    (store.root / assets[0].file.relative_key).write_bytes(b"corrupt")
    with pytest.raises(DomainError):
        resolver.select(part, selected)
    assert resolver.choices(part) == ()


def test_official_file_changed_missing_or_cache_rebuilt(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, index, part, _ = resolver_setup
    official = resolver.search(part, AssetType.SYMBOL, "R").candidates[-1]
    path = Path(index.configuration().symbols) / "Device.kicad_sym"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(DomainError, match="modifié"):
        resolver.select(part, official)
    index.rebuild(index.configuration())
    with pytest.raises(DomainError, match="indexée a changé"):
        resolver.select(part, official)
    updated = resolver.search(part, AssetType.SYMBOL, "R").candidates[-1]
    path.unlink()
    with pytest.raises(DomainError, match="indisponible"):
        resolver.select(part, updated)
    assert resolver.choices(part) == ()


def test_current_managed_choice_cannot_be_detached_or_retyped(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, assets = resolver_setup
    resolver.select(part, resolver.search(part, AssetType.SYMBOL, "R").candidates[0])
    with pytest.raises(DomainError, match="sélectionné"):
        resolver.catalogue.save(replace(part, asset_ids=()))
    with pytest.raises(ConflictError, match="sélectionné"):
        resolver.catalogue.repository.save(replace(part, asset_ids=()))
    with pytest.raises(DomainError):
        resolver.catalogue.save(replace(assets[0], asset_type=AssetType.DATASHEET))


def test_empty_result_and_unavailable_index_keep_choice(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, index, part, _ = resolver_setup
    official = resolver.search(part, AssetType.SYMBOL, "R").candidates[-1]
    resolver.select(part, official)
    clean = Part(name="No match")
    resolver.catalogue.save(clean)
    assert resolver.search(clean, AssetType.SYMBOL, "unknown").candidates == ()
    index.cache.write_bytes(b"invalid cache")
    assert resolver.search(part, AssetType.SYMBOL, "R").notices
    assert len(resolver.search(part, AssetType.SYMBOL, "R").candidates) == 2
    assert resolver.choices(part) == (official.choice,)


@pytest.mark.parametrize(
    "role,extension",
    [
        (AssetType.DATASHEET, ".pdf"),
        (AssetType.FOOTPRINT, ".kicad_mod"),
        (AssetType.MODEL_3D, ".step"),
    ],
)
def test_all_roles_and_shared_package(
    tmp_path: Path, engine: Engine, role: AssetType, extension: str
) -> None:
    repository = SqliteCatalogue(engine)
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(repository, store)
    source = tmp_path / ("Timer" + extension)
    source.write_bytes(b"fixture resource")
    asset = AssetImports(catalogue, store).import_file(
        str(source), name="Timer", origin=AssetOrigin.USER_PROVIDED, source_reference="fixture"
    )
    package = Package(name="Timer package")
    catalogue.save(package)
    part = Part(name="Timer", package_id=package.id)
    catalogue.save(part)
    catalogue.save(Part(name="Another Timer", package_id=package.id))
    owner = part if role is AssetType.DATASHEET else package
    resolver = LocalResolver(catalogue, repository)
    candidate = resolver.search(owner, role, "Timer").candidates[0]
    resolver.select(owner, candidate)
    assert resolver.choices(owner) == (ResourceChoice(role, asset.id),)
    assert catalogue.require(type(owner), owner.id).asset_ids == (asset.id,)
    assert catalogue.require(Part, part.id).package_id == package.id
    with pytest.raises(DomainError, match="Rôle incompatible"):
        resolver.search(
            owner, AssetType.SYMBOL if isinstance(owner, Package) else AssetType.MODEL_3D, ""
        )


def test_m2_upgrade_preserves_store_links_and_has_no_implicit_selection(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "old.sqlite3")
    try:
        migrate(engine, "0002_asset_files")
        part, asset = uuid4(), uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO parts VALUES (:id,'Timer','','DRAFT',NULL)"), {"id": part.hex}
            )
            conn.execute(
                text(
                    "INSERT INTO assets VALUES (:id,'Timer','SYMBOL','USER_PROVIDED',"
                    "'fixture','UNCHECKED')"
                ),
                {"id": asset.hex},
            )
            conn.execute(
                text("INSERT INTO asset_files VALUES (:id,:hash,7,'.kicad_sym','Timer.kicad_sym')"),
                {"id": asset.hex, "hash": "a" * 64},
            )
            conn.execute(
                text("INSERT INTO part_assets VALUES (:part,:asset)"),
                {"part": part.hex, "asset": asset.hex},
            )
        migrate(engine)
        repo = SqliteCatalogue(engine)
        saved = repo.get(Part, part)
        assert saved is not None and saved.asset_ids == (asset,)
        assert repo.choices(saved) == ()
        saved_asset = repo.get(Asset, asset)
        assert saved_asset is not None and saved_asset.file is not None
        assert saved_asset.file.sha256 == "a" * 64
        migrate(engine, "0002_asset_files", downgrade=True)
        migrate(engine)
        assert repo.get(Part, part) == saved
    finally:
        engine.dispose()


@pytest.mark.parametrize("bad", ["role", "resource", "owner", "key"])
def test_choice_database_constraints(engine: Engine, bad: str) -> None:
    repo = SqliteCatalogue(engine)
    part = Part(name="Constraint")
    repo.save(part)
    values = dict(
        owner_key=f"Part:{part.id.hex}",
        asset_type="SYMBOL",
        part_id=part.id,
        package_id=None,
        asset_id=None,
        reference_json="{}",
    )
    if bad == "role":
        values["asset_type"] = "FOOTPRINT"
    if bad == "resource":
        values["reference_json"] = ""
    if bad == "owner":
        values["part_id"] = None
    if bad == "key":
        values["owner_key"] = "incorrect"
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(ChoiceRow).values(**values))


def test_concurrent_initial_choices_have_one_winner(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    resolver, _, part, _ = resolver_setup
    candidates = resolver.search(part, AssetType.SYMBOL, "R").candidates[:2]

    def choose(index: int) -> bool:
        try:
            resolver.repository.choose(part, candidates[index].choice, None)
        except ConflictError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(choose, (0, 1))) == [False, True]
    assert len(resolver.choices(part)) == 1


@pytest.mark.parametrize("role", [AssetType.FOOTPRINT, AssetType.MODEL_3D])
def test_official_mechanical_choice_roundtrip(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
    tmp_path: Path,
    role: AssetType,
) -> None:
    resolver, index, _, _ = resolver_setup
    footprints = tmp_path / "official/footprints"
    (footprints / "Test.pretty").mkdir(parents=True)
    (footprints / "Test.pretty/R.kicad_mod").write_text(
        '(footprint "R" (version 20260206) (generator fixture))'
    )
    models = tmp_path / "official/3dmodels"
    (models / "Test.3dshapes").mkdir(parents=True)
    (models / "Test.3dshapes/R.step").write_bytes(b"fixture STEP")
    index.configure(LibraryRoots(index.configuration().symbols, str(footprints), str(models)))
    index.rebuild(index.configuration())
    package = Package(name="R")
    resolver.catalogue.save(package)
    candidate = resolver.search(package, role, "R").candidates[0]
    resolver.select(package, candidate)
    assert resolver.choices(package) == (candidate.choice,)
    assert resolver.catalogue.require(Package, package.id).asset_ids == ()


def test_choice_failure_rolls_back_new_association(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
    engine: Engine,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    resolver, _, part, _ = resolver_setup
    managed = resolver.search(part, AssetType.SYMBOL, "R").candidates[1]

    def fail_choice(*args: object) -> None:
        if "INSERT INTO resource_choices" in str(args[2]):
            raise OperationalError("fixture statement", None, Exception("fixture write failure"))

    event.listen(engine, "before_cursor_execute", fail_choice)
    try:
        with pytest.raises(DomainError, match="Sélection impossible"):
            resolver.select(part, managed)
    finally:
        event.remove(engine, "before_cursor_execute", fail_choice)
    assert resolver.choices(part) == ()
    assert resolver.catalogue.require(Part, part.id).asset_ids == part.asset_ids


def test_failed_replacement_retains_existing_user_choice(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, index, part, _ = resolver_setup
    user, _, official = resolver.search(part, AssetType.SYMBOL, "R").candidates
    resolver.select(part, user)
    (Path(index.configuration().symbols) / "Device.kicad_sym").unlink()
    with pytest.raises(DomainError, match="indisponible"):
        resolver.select(part, official, expected=user.choice, replace_existing=True)
    assert resolver.choices(part) == (user.choice,)
    assert resolver.catalogue.require(Part, part.id).asset_ids == part.asset_ids


def test_available_symbol_not_blocked_by_missing_unrelated_root(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
    tmp_path: Path,
) -> None:
    resolver, index, part, _ = resolver_setup
    footprints = tmp_path / "optional-footprints"
    footprints.mkdir()
    index.configure(LibraryRoots(symbols=index.configuration().symbols, footprints=str(footprints)))
    index.rebuild(index.configuration())
    official = resolver.search(part, AssetType.SYMBOL, "R").candidates[-1]
    footprints.rmdir()
    resolver.select(part, official)
    assert resolver.choices(part) == (official.choice,)


def test_manufacturer_and_third_party_follow_all_official_tiers(
    resolver_setup: tuple[LocalResolver, LocalKiCadIndex, Part, tuple[Asset, ...]],
) -> None:
    resolver, _, part, _ = resolver_setup
    assert resolver.catalogue.store is not None
    imports = AssetImports(resolver.catalogue, resolver.catalogue.store)
    for origin, source in (
        (AssetOrigin.KICAD_OFFICIAL, "https://gitlab.com/kicad/libraries/kicad-symbols/fixture"),
        (AssetOrigin.MANUFACTURER, "https://manufacturer.example/part"),
        (AssetOrigin.TRUSTED_THIRD_PARTY, "https://www.snapeda.com/parts/fixture"),
    ):
        imports.import_content(
            b'(kicad_symbol_lib (version 20251024) (symbol "R"))',
            "R.kicad_sym",
            name="R",
            origin=origin,
            source_reference=source,
        )
    tiers = [c.tier for c in resolver.search(part, AssetType.SYMBOL, "R").candidates]
    assert tiers == [
        CandidateTier.USER,
        CandidateTier.MANAGED,
        CandidateTier.KICAD,
        CandidateTier.REMOTE,
        CandidateTier.MANUFACTURER,
        CandidateTier.THIRD_PARTY,
    ]
