"""Local 3D parsing, bounded conversion and verified managed/official snapshots."""

import hashlib
import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.previews import Previews
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference, LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure import model_preview as model
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.preview_reader import LocalPreviewReader

WRL = """#VRML V2.0 utf8
DEF Material Appearance { material Material { diffuseColor 0.2 0.4 0.6 } }
Transform { translation 2 3 4 rotation 0 0 1 1.5707963267948966 scale 2 2 2
 children [ Shape { appearance USE Material geometry IndexedFaceSet {
 coord DEF Points Coordinate { point [ 0 0 0, 1 0 0, 0 1 0, 0 0 1 ] }
 coordIndex [0 2 1 -1, 0 1 3 -1, 0 3 2 -1, 1 2 3 -1] } } ] }
"""


def test_vrml_material_transform_and_shared_nodes() -> None:
    mesh = model.wrl_mesh(WRL.encode())
    assert mesh.vertices[0] == (2, 3, 4)
    assert mesh.vertices[1] == pytest.approx((2, 5, 4))
    assert mesh.vertices[2] == pytest.approx((0, 3, 4))
    assert mesh.colors == ((0.2, 0.4, 0.6),) * 4
    assert len(mesh.faces) == 4 and not mesh.warnings
    repeated = WRL + "Shape { geometry IndexedFaceSet {coord USE Points coordIndex [0 1 2 -1]} }"
    assert len(model.wrl_mesh(repeated.encode()).faces) == 5


def test_vrml_center_and_scale_orientation() -> None:
    text = WRL.replace(
        "translation 2 3 4 rotation 0 0 1 1.5707963267948966 scale 2 2 2",
        "center 1 0 0 scale 2 1 1 scaleOrientation 0 0 1 1.5707963267948966",
    )
    mesh = model.wrl_mesh(text.encode())
    assert mesh.vertices[0] == pytest.approx((0, 0, 0))
    assert mesh.vertices[1] == pytest.approx((1, 0, 0))
    assert mesh.vertices[2] == pytest.approx((0, 2, 0))


@pytest.mark.parametrize(
    "content",
    [
        b"bad",
        b"#VRML V1.0 ascii\n",
        WRL[:-6].encode(),
        WRL.replace("0 2 1 -1", "0 20 1 -1").encode(),
        WRL.replace("0 2 1 -1", "0 0.5 1 -1").encode(),
        WRL.replace("0 2 1 -1", "0 2 -1").encode(),
        WRL.replace("2 3 4", "1e999 3 4").encode(),
        WRL.replace("scale 2 2 2", "scale 0 2 2").encode(),
        WRL.replace("IndexedFaceSet {", "IndexedFaceSet {convex FALSE").encode(),
        b'#VRML V2.0 utf8\nInline { url "https://invalid.invalid/model.wrl" }',
        b'#VRML V2.0 utf8\nScript { url "file:///tmp/script.py" }',
        b"#VRML V2.0 utf8\nShape { geometry Box {} }",
        b"#VRML V2.0 utf8\nUSE Unknown",
        b"#VRML V2.0 utf8\n" + b"Group {children [" * 60 + b"]}" * 60,
    ],
)
def test_invalid_or_unsupported_wrl_is_explicit(content: bytes) -> None:
    with pytest.raises(DomainError):
        model.wrl_mesh(content)


def test_wrl_limit_and_incomplete_appearance(monkeypatch: pytest.MonkeyPatch) -> None:
    text = WRL.replace("diffuseColor 0.2 0.4 0.6", "diffuseColor 0.2 0.4 0.6 transparency 0.5")
    assert "Transparence" in model.wrl_mesh(text.encode()).warnings[0]
    monkeypatch.setattr(model, "MAX_FACES", 3)
    with pytest.raises(DomainError, match="faces"):
        model.wrl_mesh(WRL.encode())


def test_3d_snapshot_provenance_and_corruption(engine: Engine, tmp_path: Path) -> None:
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(SqliteCatalogue(engine), store)
    asset = AssetImports(catalogue, store).import_content(
        WRL.encode(),
        "fixture.wrl",
        name="Fixture 3D",
        origin=AssetOrigin.USER_PROVIDED,
        source_reference="local fixture",
    )
    index = LocalKiCadIndex(tmp_path / "index")
    reader = LocalPreviewReader(store, index)
    service = Previews(catalogue, reader)
    choice = ResourceChoice(AssetType.MODEL_3D, asset_id=asset.id)
    preview = service.inspect(choice)
    assert preview.content.mesh is not None
    assert preview.sha256 == hashlib.sha256(WRL.encode()).hexdigest()
    assert catalogue.require(Asset, asset.id) == asset
    root = tmp_path / "official"
    root.mkdir()
    path = root / "model.wrl"
    path.write_bytes(WRL.encode())
    index.configure(LibraryRoots(models=str(root)))
    ref = KiCadReference(
        asset_type=AssetType.MODEL_3D,
        library="Fixture",
        name="Model",
        relative_path="model.wrl",
        sha256=preview.sha256,
    )
    assert service.inspect(ResourceChoice(AssetType.MODEL_3D, reference=ref)).content.mesh
    assert path.read_bytes() == WRL.encode()
    with pytest.raises(DomainError, match="portable|sort"):
        reader.official(replace(ref, relative_path="../escape.wrl"))
    path.write_bytes(b"changed")
    with pytest.raises(DomainError, match="corrompu"):
        reader.official(ref)
    assert asset.file is not None
    store._path(asset.file).write_bytes(b"changed")
    with pytest.raises(DomainError, match="corrompu"):
        service.inspect(choice)


def test_step_without_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model, "freecad_command", lambda: None)
    with pytest.raises(DomainError, match="FreeCAD"):
        model.step_mesh(b"ISO-10303-21; fixture")
    with pytest.raises(DomainError, match="En-tête"):
        model.step_mesh(b"not STEP")


def test_step_isolated_snapshot_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model, "freecad_command", lambda: "/fixture/freecadcmd")
    directories: list[Path] = []

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        environment = kwargs["env"]
        source = Path(environment["KIPART_PREVIEW_INPUT"])
        assert source.read_bytes() == b"ISO-10303-21; fixture"
        assert args[1] == "-u" and args[3] == "-s"
        assert kwargs["cwd"] == source.parent and kwargs["timeout"] == 30
        assert "PYTHONPATH" not in environment
        directories.append(source.parent)
        Path(environment["KIPART_PREVIEW_OUTPUT"]).write_text(
            json.dumps(
                {
                    "vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                    "faces": [[0, 1, 2]],
                }
            )
        )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    mesh = model.step_mesh(b"ISO-10303-21; fixture")
    assert mesh.faces == ((0, 1, 2),) and mesh.warnings
    assert all(not path.exists() for path in directories)


@pytest.mark.parametrize("failure", ["timeout", "crash", "bad mesh", "nan", "large"])
def test_step_failures(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    monkeypatch.setattr(model, "freecad_command", lambda: "/fixture/freecadcmd")

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 30)
        if failure == "crash":
            return subprocess.CompletedProcess(args, 1)
        output = Path(kwargs["env"]["KIPART_PREVIEW_OUTPUT"])
        if failure == "large":
            output.write_bytes(b"x" * (model.MAX_OUTPUT + 1))
        else:
            output.write_text(
                json.dumps({"vertices": [[math.nan, 0.0, 0.0]] * 3, "faces": [[0, 1, 2]]})
                if failure == "nan"
                else "{}"
            )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(DomainError):
        model.step_mesh(b"ISO-10303-21; fixture")


def test_backend_environment_path_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setenv("KIPART_FREECAD_CMD", str(missing))
    assert model.freecad_command() is None
    missing.write_text("fixture")
    assert model.freecad_command() == str(missing)
