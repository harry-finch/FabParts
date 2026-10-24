"""Deterministic metadata fixtures, read-only rebuilding and failure recovery."""

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.domain.entities import Asset, AssetType
from kipartmanager.domain.kicad import KiCadError, LibraryRoots
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex, discover_roots
from kipartmanager.infrastructure.kicad_parser import parse


@pytest.fixture
def libraries(tmp_path: Path) -> tuple[LocalKiCadIndex, LibraryRoots]:
    root = tmp_path / "official"
    symbols, footprints, models = (root / name for name in ("symbols", "footprints", "3dmodels"))
    symbols.mkdir(parents=True)
    (footprints / "Resistor_SMD.pretty").mkdir(parents=True)
    (models / "Resistor_SMD.3dshapes").mkdir(parents=True)
    (symbols / "Device.kicad_sym").write_text(
        """
(kicad_symbol_lib (version 20251024) (generator fixture)
  (symbol "R" (property "Description" "Résistance \\"précise\\" (SMD)")
    (property "ki_keywords" "resistor résistance")
    (symbol "R_0_1" (polyline (pts (xy 0 0) (xy 1 1)))))
  (symbol "R_Small" (extends "R") (property "ki_keywords" "small")))
""",
        encoding="utf-8",
    )
    (footprints / "Resistor_SMD.pretty/R_0402.kicad_mod").write_text(
        """
(footprint "R_0402" (version 20260206) (generator fixture)
 (descr "Résistance SMD") (tags "resistor small")
 (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))
""",
        encoding="utf-8",
    )
    for extension in ("step", "stp", "wrl"):
        (models / f"Resistor_SMD.3dshapes/R_0402.{extension}").write_bytes(
            b"ISO-10303-21;\nEND-ISO-10303-21;" if extension != "wrl" else b"#VRML V2.0 utf8\n"
        )
    roots = LibraryRoots(str(symbols), str(footprints), str(models))
    index = LocalKiCadIndex(tmp_path / "data")
    index.configure(roots)
    return index, roots


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_rebuild_search_reopen_and_read_only(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    tmp_path: Path,
) -> None:
    index, roots = libraries
    before = snapshot(tmp_path / "official")
    first = index.rebuild(roots)
    assert first.count == 6 and not first.issues
    references = index.search("")
    assert len(references) == 6
    assert all(not isinstance(ref, Asset) for ref in references)
    resistor = index.search("Device:R", AssetType.SYMBOL)[0]
    assert resistor.identifier == "Device:R"
    assert resistor.description == 'Résistance "précise" (SMD)'
    assert (
        resistor.sha256
        == hashlib.sha256((Path(roots.symbols) / resistor.relative_path).read_bytes()).hexdigest()
    )
    assert len(index.search("RÉSISTANCE")) == 2
    assert len(index.search("small")) == 2
    assert len(index.search("%_'")) == 0  # Literal substring, no SQL wildcard/injection.
    assert index.search("R_Small")[0].extends == "R"
    assert not index.search("R_0_1")  # Nested units are not catalogue entries.
    assert index.rebuild(roots) == first
    assert index.search("") == references
    reopened = LocalKiCadIndex(tmp_path / "data")
    assert reopened.configuration() == roots
    assert reopened.report() == first
    assert reopened.search("") == references
    assert snapshot(tmp_path / "official") == before
    assert not (tmp_path / "data/assets").exists()


@pytest.mark.parametrize("version", ["20211014", "20220914", "20231120", "20241209", "20251024"])
def test_symbol_version_metadata(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    version: str,
) -> None:
    index, roots = libraries
    path = Path(roots.symbols) / "Device.kicad_sym"
    path.write_text(path.read_text().replace("20251024", version))
    assert index.rebuild(roots).count == 6
    assert index.search("Device:R")[0].format_version == version


@pytest.mark.parametrize("version", ["20210108", "20221018", "20240108", "20241229", "20260206"])
def test_footprint_version_metadata(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    version: str,
) -> None:
    index, roots = libraries
    path = Path(roots.footprints) / "Resistor_SMD.pretty/R_0402.kicad_mod"
    path.write_text(path.read_text().replace("20260206", version))
    assert not index.rebuild(roots).issues


@pytest.mark.parametrize(
    "invalid",
    [
        '(kicad_symbol_lib (version 20990101) (symbol "Future"))',
        '(kicad_symbol_lib (version 20251024) (symbol "Broken")',
        '(kicad_symbol_lib (version 20251024) (symbol "Unterminated))',
        '(kicad_symbol_lib (symbol "NoVersion"))',
        "(kicad_symbol_lib (version 20251399))",
        '(module "Legacy")',
        '(kicad_symbol_lib (version 20251024) (symbol "R") (symbol "R"))',
        '(kicad_symbol_lib (version 20251024) (symbol "Bad:Name"))',
        "(kicad_symbol_lib (version 20251024)) trailing",
        "",
    ],
)
def test_bad_files_visible_partial_index(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    invalid: str,
) -> None:
    index, roots = libraries
    (Path(roots.symbols) / "Invalid.kicad_sym").write_text(invalid)
    report = index.rebuild(roots)
    assert report.count == 6
    assert len(report.issues) == 1
    assert report.issues[0].source == "SYMBOL/Invalid.kicad_sym"
    assert index.report() == report


def test_missing_configuration_and_roots_preserve_cache(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    tmp_path: Path,
) -> None:
    index, roots = libraries
    index.rebuild(roots)
    before = index.cache.read_bytes()
    with pytest.raises(KiCadError, match="Aucune installation"):
        index.rebuild(LibraryRoots())
    with pytest.raises(KiCadError, match="absent"):
        index.configure(LibraryRoots(symbols=str(tmp_path / "missing")))
    assert index.configuration() == roots
    Path(roots.symbols).rename(Path(roots.symbols).with_name("gone"))
    with pytest.raises(KiCadError, match="absent"):
        index.rebuild(roots)
    assert index.cache.read_bytes() == before
    empty = LocalKiCadIndex(tmp_path / "empty")
    assert empty.search("") == []
    assert empty.report().issues


def test_legacy_symlink_and_name_mismatch_reported(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
) -> None:
    index, roots = libraries
    (Path(roots.symbols) / "Legacy.lib").write_text("EESchema-LIBRARY Version 2.4")
    (Path(roots.symbols) / "Linked.kicad_sym").symlink_to("Device.kicad_sym")
    footprint = Path(roots.footprints) / "Resistor_SMD.pretty/R_0402.kicad_mod"
    footprint.write_text(footprint.read_text().replace('"R_0402"', '"Different"'))
    report = index.rebuild(roots)
    assert report.count == 5
    assert len(report.issues) == 3


def test_traversal_and_replacement_failures_preserve_cache(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    index, roots = libraries
    index.rebuild(roots)
    before = index.cache.read_bytes()
    directory = Path(roots.models) / "Linked.3dshapes"
    directory.symlink_to(Path(roots.models) / "Resistor_SMD.3dshapes", target_is_directory=True)
    with pytest.raises(KiCadError, match="symbolique"):
        index.rebuild(roots)
    assert index.cache.read_bytes() == before
    directory.unlink()

    def denied(source: object, destination: object) -> None:
        raise PermissionError("test denied")

    monkeypatch.setattr(os, "replace", denied)
    with pytest.raises(KiCadError, match="ancien cache conservé"):
        index.rebuild(roots)
    assert index.cache.read_bytes() == before
    assert list(index.cache.parent.iterdir()) == [index.cache]


def test_config_stale_cache_and_invalid_cache(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
) -> None:
    index, roots = libraries
    index.rebuild(roots)
    index.configure(LibraryRoots(symbols=roots.symbols))
    assert "Configuration modifiée" in index.report().issues[0].message
    with sqlite3.connect(index.cache) as database:
        database.execute("PRAGMA user_version=99")
    with pytest.raises(KiCadError, match="incompatible"):
        index.search("")
    index.rebuild(index.configuration())
    assert index.report().count == 2
    index.config.write_text("symbols = [invalid")
    with pytest.raises(KiCadError, match="illisible"):
        index.configuration()


def test_discovery_environment_and_manual_config(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index, roots = libraries
    for suffix, path in zip(
        ("SYMBOL_DIR", "FOOTPRINT_DIR", "3DMODEL_DIR"),
        (roots.symbols, roots.footprints, roots.models),
        strict=True,
    ):
        monkeypatch.setenv(f"KICAD10_{suffix}", path)
    assert discover_roots() == roots
    service = KiCadLibraries(index)
    assert service.discover() == roots
    assert service.rebuild().count == 6
    assert len(service.search("", AssetType.MODEL_3D, limit=2)) == 2
    with pytest.raises(KiCadError, match="Limite"):
        service.search("", limit=0)


def test_configuration_never_writes_in_library(tmp_path: Path) -> None:
    official = tmp_path / "official"
    official.mkdir()
    index = LocalKiCadIndex(official)
    with pytest.raises(KiCadError, match="hors des bibliothèques"):
        index.configure(LibraryRoots(symbols=str(official)))
    assert list(official.iterdir()) == []


def test_parser_boundaries() -> None:
    assert parse('; comment\n(root "café" (value "a\\\\b\\nc"))').value("value") == "a\\b\nc"
    for text in ("(root))", "(root) (another)", "(root ())", "(" * 129 + "x" + ")" * 129):
        with pytest.raises(KiCadError):
            parse(text)


def test_discovery_without_installation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    assert discover_roots() == LibraryRoots()


def test_portable_references_after_relocation(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    tmp_path: Path,
) -> None:
    index, roots = libraries
    index.rebuild(roots)
    references = index.search("")
    renamed = tmp_path / "other-installation"
    (tmp_path / "official").rename(renamed)
    roots = LibraryRoots(*(str(renamed / name) for name in ("symbols", "footprints", "3dmodels")))
    index.configure(roots)
    index.rebuild(roots)
    assert index.search("") == references


def test_invalid_utf8_and_unreadable_files_reported(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index, roots = libraries
    broken = Path(roots.symbols) / "Broken.kicad_sym"
    broken.write_bytes(b"\xff")
    assert len(index.rebuild(roots).issues) == 1
    original_read = index._read

    def denied(path: Path, text: bool) -> tuple[str, str]:
        if path.name == "Device.kicad_sym":
            raise PermissionError("fixture denied")
        return original_read(path, text)

    monkeypatch.setattr(index, "_read", denied)
    assert len(index.rebuild(roots).issues) == 2


def test_corrupt_cache_is_explicitly_rebuildable(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
) -> None:
    index, roots = libraries
    index.rebuild(roots)
    index.cache.write_bytes(b"broken cache")
    with pytest.raises(KiCadError, match="Cache illisible"):
        index.report()
    with pytest.raises(KiCadError, match="Cache illisible"):
        index.search("")
    index.rebuild(roots)
    assert index.report().count == 6


def test_incomplete_cache_metadata_is_reported(
    libraries: tuple[LocalKiCadIndex, LibraryRoots],
) -> None:
    index, roots = libraries
    index.rebuild(roots)
    with sqlite3.connect(index.cache) as database:
        database.execute("DELETE FROM roots")
    with pytest.raises(KiCadError, match="Métadonnées du cache invalides"):
        index.report()
    index.rebuild(roots)
    assert index.report().count == 6
