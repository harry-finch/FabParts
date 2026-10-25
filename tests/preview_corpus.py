"""Generate a NEW disposable catalogue; never opens or modifies an existing directory.

PYTHONPATH=src python -m tests.preview_corpus /tmp/fabparts-tech02-copy [--official]
"""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Collection, Package, Part
from kipartmanager.domain.kicad import KiCadReference, LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex, discover_roots

FIXTURES = Path(__file__).parent / "fixtures/previews"


def create_corpus(root: Path, official: bool = False) -> dict[str, UUID]:
    root.mkdir(parents=True, exist_ok=False)
    engine = create_database_engine(root / "database/catalogue.sqlite3")
    migrate(engine)
    repository = SqliteCatalogue(engine)
    store = LocalAssetStore(root / "assets")
    cat = Catalogue(repository, store)
    cat.initialize_defaults()
    ids: dict[str, UUID] = {}

    def asset(filename: str, symbol: str = "", data: bytes | None = None) -> Asset:
        content = data if data is not None else (FIXTURES / filename).read_bytes()
        file = store.import_content(content, filename)
        if symbol:
            file = replace(file, symbol_name=symbol)
        value = Asset(
            name=symbol or filename,
            asset_type=file.asset_type,
            origin=AssetOrigin.USER_PROVIDED,
            source="Original synthetic TECH-02A corpus · GPL-3.0-or-later",
            file=file,
        )
        cat.save(value)
        return value

    def component(name: str, symbol: str, footprint: str, pdf: Asset) -> Part:
        sym = asset("Synthetic.kicad_sym", symbol)
        fp = asset(footprint + ".kicad_mod")
        package = Package(name=footprint, asset_ids=(fp.id,))
        cat.save(package)
        part = Part(
            name=name,
            description="Corpus synthétique de vérification · aucun usage de production",
            package_id=package.id,
            asset_ids=(sym.id, pdf.id),
        )
        cat.save(part)
        repository.choose(part, ResourceChoice(AssetType.SYMBOL, asset_id=sym.id), None)
        repository.choose(part, ResourceChoice(AssetType.DATASHEET, asset_id=pdf.id), None)
        repository.choose(package, ResourceChoice(AssetType.FOOTPRINT, asset_id=fp.id), None)
        ids[name] = part.id
        return part

    pdf = asset("Synthetic.pdf")
    for name, symbol_name, footprint_name in [
        ("01 Simple DIP", "Simple", "DIP8"),
        ("02 Four sides SOIC", "FourSides", "SOIC8"),
        ("03 Multi QFP48", "Multi", "QFP48"),
        ("04 Inherited QFN", "Inherited", "QFN32_EP"),
        ("05 Passive SMD", "Simple", "R0603"),
        ("06 Connector", "FourSides", "Connector6"),
    ]:
        component(name, symbol_name, footprint_name, pdf)
    missing = asset("Missing.pdf", data=b"%PDF-1.4 missing test")
    (root / "assets" / missing.file.relative_key).unlink()  # type: ignore[union-attr]
    component("07 Missing PDF", "Simple", "R0603", missing)
    invalid = asset("Invalid.pdf", data=b"not a pdf")
    broken = component("08 Invalid files", "Simple", "R0603", invalid)
    bad = asset("Broken.kicad_sym", data=b"(kicad_symbol_lib (version 20231120) (")
    old = next(c for c in repository.choices(broken) if c.asset_type is AssetType.SYMBOL)
    broken = replace(broken, asset_ids=(*broken.asset_ids, bad.id))
    cat.save(broken)
    repository.choose(broken, ResourceChoice(AssetType.SYMBOL, asset_id=bad.id), old)
    empty = Part(name="09 Empty resources")
    cat.save(empty)
    ids[empty.name] = empty.id
    if official:
        roots = discover_roots()
        symbol = Path(roots.symbols) / "Timer.kicad_sym"
        fp = Path(roots.footprints) / "Package_DIP.pretty/DIP-8_W7.62mm.kicad_mod"
        if not roots.symbols or not symbol.is_file() or not fp.is_file():
            raise RuntimeError("Official local KiCad fixtures not installed")
        LocalKiCadIndex(root).configure(LibraryRoots(roots.symbols, roots.footprints, ""))
        package = Package(name="DIP-8_W7.62mm")
        cat.save(package)
        part = Part(name="10 NE555P official", package_id=package.id, asset_ids=(pdf.id,))
        cat.save(part)
        references: list[tuple[Part | Package, AssetType, Path, str, str, str]] = [
            (part, AssetType.SYMBOL, symbol, "Timer", "NE555P", "Timer.kicad_sym"),
            (
                package,
                AssetType.FOOTPRINT,
                fp,
                "Package_DIP",
                "DIP-8_W7.62mm",
                "Package_DIP.pretty/DIP-8_W7.62mm.kicad_mod",
            ),
        ]
        for owner, kind, path, library, name, relative in references:
            reference = KiCadReference(
                asset_type=kind,
                library=library,
                name=name,
                relative_path=relative,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            repository.choose(owner, ResourceChoice(kind, reference=reference), None)
        repository.choose(part, ResourceChoice(AssetType.DATASHEET, asset_id=pdf.id), None)
        ids[part.name] = part.id
    cat.save(Collection(name="TECH-02A · Synthetic corpus", part_ids=tuple(ids.values())))
    engine.dispose()
    (root / "TECH01_COPY.json").write_text(
        json.dumps(
            {
                "format": "fabparts-tech01-copy/1",
                "source": str(root.parent / "synthetic-source-not-production"),
            }
        )
    )
    return ids


if __name__ == "__main__":
    result = create_corpus(Path(sys.argv[1]).resolve(), "--official" in sys.argv)
    print(json.dumps({key: str(value) for key, value in result.items()}, indent=2))
