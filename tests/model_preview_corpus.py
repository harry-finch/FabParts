"""Extend only a NEW synthetic TECH-02A corpus with original 3D fixtures."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Package, Part
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine
from tests.preview_corpus import create_corpus

FIXTURES = Path(__file__).parent / "fixtures/models"


def create_model_corpus(root: Path) -> dict[str, UUID]:
    ids = create_corpus(root)
    engine = create_database_engine(root / "database/catalogue.sqlite3")
    repo = SqliteCatalogue(engine)
    store = LocalAssetStore(root / "assets")
    cat = Catalogue(repo, store)
    for base, names in [
        ("01 Simple DIP", ("box.wrl", "box.step")),
        ("02 Four sides SOIC", ("package.wrl", "package.step")),
        ("03 Multi QFP48", ("details.step",)),
        ("04 Inherited QFN", ("invalid.wrl", "invalid.step", "dynamic.wrl")),
        ("05 Passive SMD", ("missing.wrl",)),
    ]:
        part = cat.require(Part, ids[base])
        assert part.package_id
        package = cat.require(Package, part.package_id)
        added = []
        for name in names:
            content = (
                b"#VRML V2.0 utf8\n# missing fixture"
                if name == "missing.wrl"
                else (FIXTURES / name).read_bytes()
            )
            file = store.import_content(content, name)
            asset = Asset(
                name=name,
                asset_type=AssetType.MODEL_3D,
                origin=AssetOrigin.USER_PROVIDED,
                source="Original synthetic TECH-02B · GPL-3.0-or-later",
                file=file,
            )
            cat.save(asset)
            added.append(asset.id)
            if name == "missing.wrl":
                (root / "assets" / file.relative_key).unlink()
        package = replace(package, asset_ids=(*package.asset_ids, *added))
        cat.save(package)
        repo.choose(package, ResourceChoice(AssetType.MODEL_3D, asset_id=added[0]), None)
    engine.dispose()
    return ids


if __name__ == "__main__":
    print(
        json.dumps(
            {k: str(v) for k, v in create_model_corpus(Path(sys.argv[1]).resolve()).items()},
            indent=2,
        )
    )
