"""Scoped checks, warning policy, fresh-input gates and durable report migration."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import IntegrityError

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    DomainError,
    Inventory,
    Package,
    Part,
    PartState,
    StockItem,
)
from kipartmanager.domain.validation import Level
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.models import ValidationRow
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from kipartmanager.infrastructure.validation_reports import SqliteValidationReports

SYMBOL = """(kicad_symbol_lib (version 20251024) (generator fixture)
 (symbol "R" (symbol "R_1_1"
  (pin passive line (at 0 0 0) (length 1) (name "A") (number "1"))
  (pin passive line (at 1 0 180) (length 1) (name "B") (number "2")))))"""
FOOTPRINT = """(footprint "R" (version 20260206) (generator fixture)
 (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))
 (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu")))"""


def setup_case(
    tmp_path: Path, engine: Engine, symbol: str = SYMBOL, footprint: str = FOOTPRINT
) -> tuple[LocalValidation, LocalResolver, Part, Package, Collection, tuple[Asset, ...]]:
    repository = SqliteCatalogue(engine)
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(repository, store)
    imports = AssetImports(catalogue, store)
    assets = []
    for name, content in (("R.kicad_sym", symbol), ("R.kicad_mod", footprint)):
        source = tmp_path / name
        source.write_text(content)
        assets.append(imports.import_file(str(source), name="R", source_reference="fixture"))
    package = Package(name="R")
    catalogue.save(package)
    part = Part(name="R", package_id=package.id)
    catalogue.save(part)
    collection = Collection(name="Test collection", part_ids=(part.id,))
    catalogue.save(collection)
    resolver = LocalResolver(catalogue, repository)
    for owner, role in ((part, AssetType.SYMBOL), (package, AssetType.FOOTPRINT)):
        resolver.select(owner, resolver.search(owner, role, "R").candidates[0])
    assert isinstance(catalogue.store, LocalAssetStore)
    service = LocalValidation(
        catalogue,
        LocalResourceProbe(catalogue.store, LocalKiCadIndex(tmp_path / "data")),
        SqliteValidationReports(engine),
    )
    return service, resolver, part, package, collection, tuple(assets)


def test_valid_collection_scoped_pass_and_reopen(tmp_path: Path, engine: Engine) -> None:
    service, resolver, part, package, collection, assets = setup_case(tmp_path, engine)
    assert service.qualification(part).state == "UNCHECKED"
    with pytest.raises(DomainError, match="non publiable"):
        service.require_publishable(collection)
    report = service.validate(part)
    assert report.level is Level.PASS
    assert {f.sha256 for f in report.findings if f.sha256} == {
        a.file.sha256 for a in assets if a.file
    }
    assert all(a.validation_state == "UNCHECKED" for a in assets)
    report = service.validate(collection)
    assert service.require_publishable(collection) == report
    reopened = LocalValidation(service.catalogue, service.probe, SqliteValidationReports(engine))
    assert reopened.qualification(collection).eligible
    assert resolver.choices(part) and resolver.choices(package)


@pytest.mark.parametrize("case", ["package", "choice", "deprecated", "empty"])
def test_mandatory_errors_block_collection(tmp_path: Path, engine: Engine, case: str) -> None:
    service, _, part, _, collection, _ = setup_case(tmp_path, engine)
    if case == "package":
        service.catalogue.save(replace(service.catalogue.require(Part, part.id), package_id=None))
    elif case == "choice":
        other = Part(name="No choice", package_id=part.package_id)
        service.catalogue.save(other)
        service.catalogue.save(replace(collection, part_ids=(other.id,)))
    elif case == "deprecated":
        service.catalogue.save(
            replace(service.catalogue.require(Part, part.id), state=PartState.DEPRECATED)
        )
    else:
        service.catalogue.save(replace(collection, part_ids=()))
    report = service.validate(collection)
    assert report.level is Level.ERROR
    service.validate(collection, accept_warnings=True)
    with pytest.raises(DomainError):
        service.require_publishable(collection)


@pytest.mark.parametrize(
    "symbol",
    [
        SYMBOL.replace('(number "2")', '(number "3")'),
        SYMBOL[:-1],
        SYMBOL.replace("20251024", "20990101"),
        SYMBOL.replace("(length 1)", "(length -1)"),
        SYMBOL.replace("(at 0 0 0)", "(at nan 0 0)"),
        '(kicad_symbol_lib (version 20251024) (symbol "R"))',
        '(kicad_symbol_lib (version 20251024) (symbol "R" (extends "Absent")))',
        '(kicad_symbol_lib (version 20251024) (symbol "R" (extends "R")))',
        SYMBOL[:-1] + ' (symbol "Other"))',
    ],
)
def test_invalid_symbols_and_pin_pad_mismatch(tmp_path: Path, engine: Engine, symbol: str) -> None:
    service, _, _, _, collection, _ = setup_case(tmp_path, engine, symbol=symbol)
    assert service.validate(collection).level is Level.ERROR
    assert not service.qualification(collection).eligible


@pytest.mark.parametrize(
    "footprint",
    [
        FOOTPRINT.replace("(size 1 1)", "(size 0 1)"),
        FOOTPRINT.replace("(size 1 1)", "(size nan 1)"),
        FOOTPRINT.replace('"F.Cu"', '"F.SilkS"'),
        FOOTPRINT.replace('(pad "1"', '(pad ""'),
        FOOTPRINT.replace(" smd rect", " unknown rect"),
        FOOTPRINT.replace("20260206", "20990101"),
        FOOTPRINT[:-1],
        '(footprint "R" (version 20260206))',
        FOOTPRINT[:-1]
        + ' (model "R.step" (scale (xyz 0 1 1)) (rotate (xyz 0 0 0)) (offset (xyz 0 0 0))))',
    ],
)
def test_invalid_footprints(tmp_path: Path, engine: Engine, footprint: str) -> None:
    service, _, _, _, collection, _ = setup_case(tmp_path, engine, footprint=footprint)
    assert service.validate(collection).level is Level.ERROR


def test_warning_policy_extra_pads_and_hint(tmp_path: Path, engine: Engine) -> None:
    footprint = FOOTPRINT[:-1] + ' (pad "3" smd rect (at 2 0) (size 1 1) (layers "F.Cu")))'
    symbol = SYMBOL.replace('(symbol "R"', '(symbol "R" (property "Footprint" "Library:Other")', 1)
    service, _, _, _, collection, _ = setup_case(tmp_path, engine, symbol, footprint)
    with pytest.raises(DomainError, match="rapport actuel"):
        service.validate(collection, accept_warnings=True)
    report = service.validate(collection)
    assert report.level is Level.WARNING and not report.eligible
    assert any(f.code.endswith("FOOTPRINT_HINT") for f in report.findings)
    assert any(f.code.endswith("EXTRA_PADS") for f in report.findings)
    with pytest.raises(DomainError):
        service.require_publishable(collection)
    service.validate(collection, accept_warnings=True)
    assert service.require_publishable(collection).warnings_accepted


@pytest.mark.parametrize(
    "extension,content,valid",
    [
        (".step", b"ISO-10303-21;\nEND-ISO-10303-21;", True),
        (".stp", b"ISO-10303-21;\nEND-ISO-10303-21;", True),
        (".wrl", b"#VRML V2.0 utf8\n", True),
        (".step", b"ISO-10303-21;", False),
        (".wrl", b"invalid", False),
    ],
)
def test_models_never_receive_unfounded_geometry_pass(
    tmp_path: Path, engine: Engine, extension: str, content: bytes, valid: bool
) -> None:
    service, resolver, _, package, collection, _ = setup_case(tmp_path, engine)
    source = tmp_path / ("R" + extension)
    source.write_bytes(content)
    assert service.catalogue.store is not None
    AssetImports(service.catalogue, service.catalogue.store).import_file(str(source), name="R")
    resolver.select(package, resolver.search(package, AssetType.MODEL_3D, "R").candidates[0])
    report = service.validate(collection)
    assert report.level is (Level.WARNING if valid else Level.ERROR)
    if valid:
        assert any("non certifiés" in f.message for f in report.findings)
        assert not service.qualification(collection).eligible
        service.validate(collection, accept_warnings=True)
        assert service.qualification(collection).eligible


@pytest.mark.parametrize(
    "change", ["part", "package", "asset", "membership", "choice", "corruption"]
)
def test_relevant_changes_invalidate_previous_pass(
    tmp_path: Path, engine: Engine, change: str
) -> None:
    service, resolver, part, package, collection, assets = setup_case(tmp_path, engine)
    previous = service.validate(collection)
    if change == "part":
        service.catalogue.save(
            replace(service.catalogue.require(Part, part.id), description="changed")
        )
    elif change == "package":
        service.catalogue.save(
            replace(service.catalogue.require(Package, package.id), description="changed")
        )
    elif change == "asset":
        service.catalogue.save(replace(assets[0], source="changed provenance"))
    elif change == "membership":
        service.catalogue.save(replace(collection, part_ids=()))
    elif change == "choice":
        source = tmp_path / "New.kicad_sym"
        source.write_text(SYMBOL)
        assert service.catalogue.store is not None
        asset = AssetImports(service.catalogue, service.catalogue.store).import_file(
            str(source), name="R"
        )
        candidate = next(
            c
            for c in resolver.search(part, AssetType.SYMBOL, "R").candidates
            if c.choice.asset_id == asset.id
        )
        resolver.select(part, candidate, expected=resolver.choices(part)[0], replace_existing=True)
    else:
        assert assets[0].file is not None and isinstance(service.catalogue.store, LocalAssetStore)
        (service.catalogue.store.root / assets[0].file.relative_key).write_bytes(b"corrupt")
    qualification = service.qualification(collection)
    assert qualification.state == "STALE" and qualification.report == previous
    assert not qualification.eligible
    with pytest.raises(DomainError):
        service.require_publishable(collection)
    with pytest.raises(DomainError):
        service.validate(collection, accept_warnings=True)


def test_stock_quantity_does_not_invalidate(tmp_path: Path, engine: Engine) -> None:
    service, _, part, _, collection, _ = setup_case(tmp_path, engine)
    service.validate(collection)
    inventory = Inventory(name="Test stock")
    service.catalogue.save(inventory)
    stock = StockItem(part_id=part.id, inventory_id=inventory.id, quantity=0)
    service.catalogue.save(stock)
    service.catalogue.save(replace(stock, quantity=3))
    assert service.qualification(collection).eligible


def test_inherited_symbol_metadata_and_pins(tmp_path: Path, engine: Engine) -> None:
    # Managed libraries cannot pick an entry; directly exercise the official parser selection.
    from kipartmanager.infrastructure.kicad_parser import parse
    from kipartmanager.infrastructure.resource_probe import symbol_info

    content = SYMBOL[:-1] + ' (symbol "Derived" (extends "R") (property "Footprint" "Test:R")))'
    name, pins, hint = symbol_info(parse(content), "Derived")
    assert (name, pins, hint) == ("Derived", ("1", "2"), "Test:R")


@pytest.mark.parametrize("bad", ["subject", "key", "empty"])
def test_validation_constraints(engine: Engine, bad: str) -> None:
    repo = SqliteCatalogue(engine)
    part = Part(name="Test")
    repo.save(part)
    values: dict[str, Any] = dict(
        subject_key=f"Part:{part.id.hex}", part_id=part.id, collection_id=None, report_json="{}"
    )
    if bad == "subject":
        values["part_id"] = None
    elif bad == "key":
        values["subject_key"] = "wrong"
    else:
        values["report_json"] = ""
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(insert(ValidationRow).values(**values))


def test_m4_upgrade_preserves_choices_and_downgrade_keeps_assets(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "m4.sqlite3")
    try:
        migrate(engine)
        service, resolver, part, package, collection, assets = setup_case(tmp_path, engine)
        choices = resolver.choices(part) + resolver.choices(package)
        # The current ORM targets HEAD; exercise the historical schema via downgrade.
        migrate(engine, "0003_resource_choices", downgrade=True)
        migrate(engine)
        service.validate(collection)
        assert resolver.choices(part) + resolver.choices(package) == choices
        assert all(service.catalogue.require(Asset, a.id) == a for a in assets)
        migrate(engine, "0003_resource_choices", downgrade=True)
        assert resolver.choices(part) + resolver.choices(package) == choices
        migrate(engine)
        assert service.qualification(collection).state == "UNCHECKED"
    finally:
        engine.dispose()


def test_warning_acceptance_invalidated_and_not_reused(tmp_path: Path, engine: Engine) -> None:
    footprint = FOOTPRINT[:-1] + ' (pad "3" smd rect (at 2 0) (size 1 1) (layers "F.Cu")))'
    service, _, part, _, collection, _ = setup_case(tmp_path, engine, footprint=footprint)
    service.validate(collection)
    service.validate(collection, accept_warnings=True)
    service.catalogue.save(replace(service.catalogue.require(Part, part.id), name="Changed"))
    assert service.qualification(collection).state == "STALE"
    with pytest.raises(DomainError):
        service.validate(collection, accept_warnings=True)
    assert not service.validate(collection).warnings_accepted
    assert not service.qualification(collection).eligible


def test_ruleset_change_and_corrupt_report_block_gate(tmp_path: Path, engine: Engine) -> None:
    import json

    service, _, _, _, collection, _ = setup_case(tmp_path, engine)
    service.validate(collection)
    with engine.begin() as connection:
        data = json.loads(connection.scalar(text("SELECT report_json FROM validation_reports")))
        data["ruleset"] = "old-rules"
        connection.execute(
            text("UPDATE validation_reports SET report_json=:data"), {"data": json.dumps(data)}
        )
    assert service.qualification(collection).state == "STALE"
    with pytest.raises(DomainError):
        service.require_publishable(collection)
    with engine.begin() as connection:
        connection.execute(text("UPDATE validation_reports SET report_json='invalid'"))
    with pytest.raises(DomainError, match="illisible"):
        service.require_publishable(collection)
    service.validate(collection)
    assert service.qualification(collection).eligible


def test_pdf_is_integrity_only_and_generated_assets_need_review(
    tmp_path: Path, engine: Engine
) -> None:
    service, resolver, part, _, collection, assets = setup_case(tmp_path, engine)
    service.catalogue.save(replace(assets[0], origin=AssetOrigin.GENERATED_PARAMETRIC))
    source = tmp_path / "sheet.pdf"
    source.write_bytes(b"opaque bytes")
    assert service.catalogue.store is not None
    AssetImports(service.catalogue, service.catalogue.store).import_file(str(source), name="sheet")
    resolver.select(part, resolver.search(part, AssetType.DATASHEET, "sheet").candidates[0])
    report = service.validate(collection)
    assert report.level is Level.WARNING
    assert any(f.code.endswith("GENERATED_REVIEW") for f in report.findings)
    assert any("PDF non certifiés" in f.message for f in report.findings)
    assert not service.qualification(collection).eligible


def test_edit_during_report_save_cannot_create_current_qualification(
    tmp_path: Path,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kipartmanager.domain.validation import ValidationReport

    service, _, part, _, collection, _ = setup_case(tmp_path, engine)
    original_save = service.repository.save_report

    def changed(subject: Part | Collection, report: ValidationReport) -> None:
        service.catalogue.save(
            replace(service.catalogue.require(Part, part.id), description="concurrent")
        )
        original_save(subject, report)

    monkeypatch.setattr(service.repository, "save_report", changed)
    assert service.validate(collection).level is Level.PASS
    assert service.qualification(collection).state == "STALE"
    with pytest.raises(DomainError):
        service.require_publishable(collection)


def test_unselected_footprint_model_dependency_is_warning(tmp_path: Path, engine: Engine) -> None:
    footprint = (
        FOOTPRINT[:-1]
        + ' (model "${KICAD10_3DMODEL_DIR}/R.step" '
        + "(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))"
    )
    service, _, _, _, collection, _ = setup_case(tmp_path, engine, footprint=footprint)
    report = service.validate(collection)
    assert report.level is Level.WARNING
    assert any(f.code.endswith("MODEL_NOT_SELECTED") for f in report.findings)
    assert not service.qualification(collection).eligible


def test_altered_findings_cannot_bypass_current_errors(tmp_path: Path, engine: Engine) -> None:
    import json

    service, _, _, _, collection, _ = setup_case(tmp_path, engine, symbol="malformed")
    assert service.validate(collection).level is Level.ERROR
    with engine.begin() as connection:
        data = json.loads(connection.scalar(text("SELECT report_json FROM validation_reports")))
        for finding in data["findings"]:
            finding["level"] = "PASS"
        connection.execute(
            text("UPDATE validation_reports SET report_json=:data"), {"data": json.dumps(data)}
        )
    assert service.qualification(collection).state == "STALE"
    with pytest.raises(DomainError):
        service.require_publishable(collection)
    with pytest.raises(DomainError):
        service.validate(collection, accept_warnings=True)
