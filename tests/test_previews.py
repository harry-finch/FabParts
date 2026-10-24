"""Read-only previews: geometry, inheritance, units and content identity."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.previews import Previews
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference, LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_preview import arc_points, drawings
from kipartmanager.infrastructure.preview_reader import LocalPreviewReader

SYMBOL = """(kicad_symbol_lib (version 20251024) (generator fixture)
(symbol "Base" (pin_names (offset 0.5))
 (symbol "Base_0_1" (rectangle (start -2 2) (end 2 -2)
  (stroke (width 0.15) (type default)) (fill (type background))))
 (symbol "Base_1_1" (pin passive line (at -5 1 0) (length 3)
  (name "IN" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1))))))
 (symbol "Base_2_1" (pin passive line (at 5 -1 180) (length 3)
  (name "OUT" (effects (font (size 1 1)))) (number "2" (effects (font (size 1 1)))))))
(symbol "Child" (extends "Base")))"""

FOOTPRINT = """(footprint "SOIC fixture" (version 20251024) (generator fixture)
(fp_rect (start -2 -2) (end 2 2) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))
(fp_poly (pts (xy -2 -3) (xy -1 -3) (xy -1 -2) (xy -2 -3))
 (stroke (width 0.1) (type solid)) (fill yes) (layer "F.Fab"))
(fp_arc (start 1 0) (mid 0 -1) (end -1 0)
 (stroke (width 0.1) (type solid)) (layer "F.CrtYd"))
(pad "1" smd roundrect (at -3 0 90) (size 1 2) (layers "F.Cu" "F.Paste" "F.Mask")
 (roundrect_rratio 0.25))
(pad "2" thru_hole oval (at 3 0) (size 2 3) (drill 1) (layers "*.Cu" "*.Mask")))"""


def test_symbol_inheritance_unit_selection_and_coordinate_orientation() -> None:
    result = drawings(SYMBOL, AssetType.SYMBOL, "Child")
    assert [d.unit for d in result] == [1, 2]
    assert all(d.name == "Child" for d in result)
    first = result[0].primitives
    assert next(p for p in first if p.kind == "rect").points == ((-2, -2), (2, 2))
    assert next(p for p in first if p.layer == "Pins" and p.kind == "line").points == (
        (-5, -1),
        (-2, -1),
    )
    assert {p.text for p in first if p.kind == "text"} == {"IN", "1"}
    assert {p.text for p in result[1].primitives if p.kind == "text"} == {"OUT", "2"}
    assert len(drawings(SYMBOL, AssetType.SYMBOL)) == 4


def test_footprint_layers_rotation_drilling_and_pad_one() -> None:
    drawing = drawings(FOOTPRINT, AssetType.FOOTPRINT)[0]
    assert not drawing.warnings
    pad1 = next(p for p in drawing.primitives if p.layer == "Pad1")
    assert pad1.angle == -90
    assert pad1.points == ((-3, 0), (1, 2))
    assert {"F.SilkS", "F.Fab", "F.CrtYd", "Pad1", "Pads", "Drill"}.issubset(
        {p.layer for p in drawing.primitives}
    )
    polygon = next(p for p in drawing.primitives if p.kind == "polygon")
    assert polygon.points == ((-2, -3), (-1, -3), (-1, -2), (-2, -3))
    assert arc_points((1, 0), (0, -1), (-1, 0))[24] == pytest.approx((0, -1))


def test_partial_geometry_has_explicit_warning() -> None:
    source = FOOTPRINT.replace("smd roundrect", "smd custom")
    drawing = drawings(source, AssetType.FOOTPRINT)[0]
    assert any("custom" in w for w in drawing.warnings)
    assert not any(p.layer == "Pad1" for p in drawing.primitives)


@pytest.mark.parametrize(
    "source,kind,selected",
    [
        ("(", AssetType.SYMBOL, ""),
        (SYMBOL, AssetType.SYMBOL, "Missing"),
        (SYMBOL.replace('(extends "Base")', '(extends "Child")'), AssetType.SYMBOL, "Child"),
        (FOOTPRINT.replace("(size 1 2)", "(size nan 2)"), AssetType.FOOTPRINT, ""),
        (FOOTPRINT.replace("(size 1 2)", "(size -1 2)"), AssetType.FOOTPRINT, ""),
        (FOOTPRINT.replace("20251024", "20300101"), AssetType.FOOTPRINT, ""),
        (FOOTPRINT.replace("(mid 0 -1)", "(mid 0 0)"), AssetType.FOOTPRINT, ""),
    ],
)
def test_invalid_preview_fails_explicitly(source: str, kind: AssetType, selected: str) -> None:
    with pytest.raises(DomainError):
        drawings(source, kind, selected)


def test_verified_snapshot_preserves_catalogue_store_and_official_files(
    engine: Engine, tmp_path: Path
) -> None:
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(SqliteCatalogue(engine), store)
    source = tmp_path / "fixture.kicad_mod"
    source.write_text(FOOTPRINT)
    asset = AssetImports(catalogue, store).import_file(str(source))
    roots = tmp_path / "official"
    roots.mkdir()
    official = roots / "fixture.kicad_mod"
    official.write_text(FOOTPRINT)
    index = LocalKiCadIndex(tmp_path / "index")
    index.configure(LibraryRoots(footprints=str(roots)))
    preview = Previews(catalogue, LocalPreviewReader(store, index))
    choice = ResourceChoice(AssetType.FOOTPRINT, asset_id=asset.id)
    result = preview.inspect(choice)
    assert result.content.drawings[0].name == "SOIC fixture"
    assert result.origin == asset.origin.value
    assert catalogue.require(Asset, asset.id) == asset
    assert asset.file is not None
    assert (store.root / asset.file.relative_key).read_bytes() == source.read_bytes()
    ref = KiCadReference(
        asset_type=AssetType.FOOTPRINT,
        library="Fixture",
        name="SOIC",
        relative_path=official.name,
        sha256=hashlib.sha256(official.read_bytes()).hexdigest(),
    )
    before = official.read_bytes()
    assert (
        preview.inspect(ResourceChoice(AssetType.FOOTPRINT, reference=ref)).origin
        == "KICAD_OFFICIAL"
    )
    assert official.read_bytes() == before
    assert len(list((store.root / "blobs").glob("*/*"))) == 1
    official.write_text(FOOTPRINT + "\n")
    with pytest.raises(DomainError, match="modifié"):
        preview.inspect(ResourceChoice(AssetType.FOOTPRINT, reference=ref))
    (store.root / asset.file.relative_key).write_bytes(b"corrupt")
    with pytest.raises(DomainError, match="corrompu"):
        preview.inspect(choice)
    with pytest.raises(DomainError):
        preview.inspect(
            ResourceChoice(AssetType.FOOTPRINT, reference=replace(ref, sha256="0" * 64))
        )


def test_missing_file_type_and_3d_are_explicit(engine: Engine, tmp_path: Path) -> None:
    catalogue = Catalogue(SqliteCatalogue(engine))
    asset = Asset(name="No file", asset_type=AssetType.SYMBOL, origin=AssetOrigin.USER_PROVIDED)
    catalogue.save(asset)
    service = Previews(
        catalogue, LocalPreviewReader(LocalAssetStore(tmp_path), LocalKiCadIndex(tmp_path))
    )
    with pytest.raises(DomainError, match="Aucun fichier"):
        service.inspect(ResourceChoice(AssetType.SYMBOL, asset_id=asset.id))
    with pytest.raises(DomainError, match="Aucun fichier"):
        service.inspect(ResourceChoice(AssetType.MODEL_3D, asset_id=asset.id))


def test_pdf_snapshot_and_header() -> None:
    content = b"%PDF-1.7\nfixture"
    assert LocalPreviewReader.decode(content, AssetType.DATASHEET).pdf == content
    with pytest.raises(DomainError, match="PDF"):
        LocalPreviewReader.decode(b"bad", AssetType.DATASHEET)


def test_pin_identifiers_remain_inspectable_when_kicad_hides_labels() -> None:
    source = SYMBOL.replace(
        "(pin_names (offset 0.5))", "(pin_names (offset 0.5) hide) (pin_numbers hide)"
    )
    drawing = drawings(source, AssetType.SYMBOL, "Child")[0]
    assert {p.text for p in drawing.primitives if p.kind == "text"} == {"IN", "1"}


def test_footprint_annotations_are_separate_from_pad_labels() -> None:
    source = FOOTPRINT.replace(
        "(generator fixture)",
        "(generator fixture) "
        '(fp_text value "SOIC" (at 0 0) (layer "F.Fab") '
        "(effects (font (size 1 1))))",
    )
    drawing = drawings(source, AssetType.FOOTPRINT)[0]
    assert next(p for p in drawing.primitives if p.kind == "annotation").text == "SOIC"
    assert {p.text for p in drawing.primitives if p.kind == "text"} == {"1", "2"}
