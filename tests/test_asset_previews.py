"""TECH-02A resolution, geometry, bounded transport and immutable sources."""

import base64
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.domain.entities import Asset, AssetType, DomainError, Part
from kipartmanager.headless_ipc import MAX_RESPONSE, respond, serve
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews
from kipartmanager.ports.previews import PDF_CHUNK, PDF_LIMIT, PreviewProblem
from tests.preview_corpus import FIXTURES, create_corpus
from tests.test_headless import hashes, reader_for, request


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, dict[str, UUID]]:
    root = tmp_path / "copy"
    return root, create_corpus(root)


def test_business_resolution_geometry_pdf_and_immutability(
    corpus: tuple[Path, dict[str, UUID]],
) -> None:
    root, ids = corpus
    before = hashes(root)
    engine, reader = reader_for(root)
    previews = AssetPreviews(reader, ReadonlyPreviews(root))
    try:
        for name, pads in [
            ("01 Simple DIP", 8),
            ("02 Four sides SOIC", 8),
            ("03 Multi QFP48", 48),
            ("04 Inherited QFN", 33),
            ("05 Passive SMD", 2),
            ("06 Connector", 6),
        ]:
            result = previews.get(str(ids[name]), "FOOTPRINT")
            assert result["status"] == "ready" and result["selected"]
            drawing = result["drawings"][0]
            assert drawing["units"] == "mm" and drawing["bounds"][2] > 0
            assert len([p for p in drawing["primitives"] if p["layer"] == "PadLabel"]) == pads
            assert {"F.Fab", "F.SilkS", "F.CrtYd"} <= {p["layer"] for p in drawing["primitives"]}
        result = previews.get(str(ids["04 Inherited QFN"]), "SYMBOL")
        assert {(d["unit"], d["style"]) for d in result["drawings"]} == {
            (1, 1),
            (1, 2),
            (2, 1),
            (2, 2),
        }
        result = previews.get(str(ids["01 Simple DIP"]), "DATASHEET")
        assert "pdf" not in result and "bytes" not in result
        handle = result["handle"]
        data = b"".join(
            base64.b64decode(previews.chunk(handle, n)["data"])
            for n in range(0, result["size_bytes"], PDF_CHUNK)
        )
        assert data == (FIXTURES / "Synthetic.pdf").read_bytes()
        previews.release(handle)
        with pytest.raises(DomainError, match="expiré"):
            previews.chunk(handle, 0)
        assert previews.get(str(ids["07 Missing PDF"]), "DATASHEET")["status"] == "missing"
        assert previews.get(str(ids["08 Invalid files"]), "DATASHEET")["status"] == "error"
        assert previews.get(str(ids["08 Invalid files"]), "SYMBOL")["status"] == "error"
        assert previews.get(str(ids["09 Empty resources"]), "SYMBOL")["status"] == "absent"
        assert previews.get(str(ids["01 Simple DIP"]), "MODEL_3D")["status"] == "unsupported"
        assert (
            previews.get(str(ids["01 Simple DIP"]), "SYMBOL", str(uuid4()))["status"]
            == "inaccessible"
        )
        part = reader.catalogue.require(Part, ids["01 Simple DIP"])
        selected = next(
            c.asset_id for c in reader.repository.choices(part) if c.asset_type is AssetType.SYMBOL
        )
        assert previews.get(str(ids["01 Simple DIP"]), "SYMBOL", str(selected))["selected"]
        broken = reader.catalogue.require(Part, ids["08 Invalid files"])
        associated_id = next(
            i for i in broken.asset_ids if reader.catalogue.require(Asset, i).name == "Simple"
        )
        associated = previews.get(str(broken.id), "SYMBOL", str(associated_id))
        assert associated["status"] == "ready" and not associated["selected"]
        assert not reader.component(ids["01 Simple DIP"])["preview_available"]
    finally:
        previews.clear()
        engine.dispose()
    assert hashes(root) == before


def test_pdf_expiry_eviction_and_chunk_limits(corpus: tuple[Path, dict[str, UUID]]) -> None:
    root, ids = corpus
    engine, reader = reader_for(root)
    service = AssetPreviews(reader, ReadonlyPreviews(root))
    try:
        handles = [service.get(str(ids["01 Simple DIP"]), "DATASHEET")["handle"] for _ in range(3)]
        assert len(service.handles) == 2 and handles[0] not in service.handles
        service.handles[handles[1]] = (0, b"expired")
        with pytest.raises(DomainError):
            service.chunk(handles[1], 0)
        with pytest.raises(DomainError):
            service.chunk(handles[2], 1)
        service.handles[handles[2]] = (float("inf"), b"x" * (PDF_CHUNK + 7))
        assert len(service.chunk(handles[2], 0)["data"]) < 90000
        assert base64.b64decode(service.chunk(handles[2], PDF_CHUNK)["data"]) == b"x" * 7
        service.clear()
        assert not service.handles
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "command,params",
    [
        ("get_asset_preview", {"id": str(uuid4()), "role": "SYMBOL", "path": "/private/file"}),
        ("get_asset_preview", {"id": "../file", "role": "SYMBOL"}),
        ("get_asset_preview", {"id": str(uuid4()), "role": "INVALID"}),
        ("read_pdf_chunk", {"handle": "/tmp/pdf", "offset": 0}),
        ("read_pdf_chunk", {"handle": "a" * 48, "offset": PDF_LIMIT}),
        ("read_pdf_chunk", {"handle": "a" * 48, "offset": True}),
        ("read_pdf_chunk", {"handle": "a" * 48}),
        ("release_preview", {"handle": "a" * 48, "path": "a"}),
    ],
)
def test_ipc_refuses_invalid_capabilities(
    corpus: tuple[Path, dict[str, UUID]], command: str, params: dict[str, Any]
) -> None:
    root, _ = corpus
    engine, reader = reader_for(root)
    try:
        assert respond(request(command, params), reader)["error"]["code"] == "INVALID_PARAMS"
    finally:
        engine.dispose()


def test_read_limits_escape_integrity_cache(tmp_path: Path) -> None:
    import hashlib

    reader = ReadonlyPreviews(tmp_path)
    root = tmp_path / "allowed"
    root.mkdir()
    good = (FIXTURES / "DIP8.kicad_mod").read_bytes()
    digest = hashlib.sha256(good).hexdigest()
    path = root / "footprint"
    path.write_bytes(good)
    first = reader.read(root, "footprint", digest, AssetType.FOOTPRINT)
    assert reader.read(root, "footprint", digest, AssetType.FOOTPRINT) is first
    path.write_bytes(b"changed")
    with pytest.raises(PreviewProblem, match="corrompu"):
        reader.read(root, "footprint", digest, AssetType.FOOTPRINT)
    outside = tmp_path / "private"
    outside.write_bytes(good)
    (root / "escape").symlink_to(outside)
    for relative in ["escape", "../private", str(outside)]:
        with pytest.raises(PreviewProblem, match="périmètre"):
            reader.read(root, relative, digest, AssetType.FOOTPRINT)
    with path.open("wb") as stream:
        stream.truncate(PDF_LIMIT + 1)
    with pytest.raises(PreviewProblem, match="16 Mio"):
        reader.read(root, "footprint", digest, AssetType.DATASHEET)
    if hasattr(os, "mkfifo"):
        os.mkfifo(root / "fifo")
        with pytest.raises(PreviewProblem, match="régulier"):
            reader.read(root, "fifo", digest, AssetType.SYMBOL)
    future = good.replace(b"20240108", b"20990101")
    path.write_bytes(future)
    with pytest.raises(PreviewProblem) as unsupported:
        reader.read(root, "footprint", hashlib.sha256(future).hexdigest(), AssetType.FOOTPRINT)
    assert unsupported.value.status == "unsupported"


def test_preview_ipc_and_headless_without_qt(corpus: tuple[Path, dict[str, UUID]]) -> None:
    root, ids = corpus
    before = hashes(root)
    engine, reader = reader_for(root)
    service = AssetPreviews(reader, ReadonlyPreviews(root))
    messages = (
        request("get_asset_preview", {"id": str(ids["03 Multi QFP48"]), "role": "FOOTPRINT"})
        + request("health")
        + request("shutdown")
    )
    output = io.BytesIO()
    serve(reader, io.BytesIO(messages), output, service)
    assert all(len(line) <= MAX_RESPONSE for line in output.getvalue().splitlines())
    engine.dispose()
    code = """import importlib.abc, sys, socket
def no_network(*args, **kwargs): raise RuntimeError("network forbidden")
socket.socket.connect = no_network
socket.create_connection = no_network
class DenyQt(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('PySide6','shiboken6')): raise ImportError(fullname)
sys.meta_path.insert(0,DenyQt())
from kipartmanager.headless import main
raise SystemExit(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", code, "--data-dir", str(root)],
        input=messages,
        capture_output=True,
        timeout=15,
        check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0]["result"]["status"] == "ready"
    assert not replies[1]["result"]["qt_loaded"]
    assert hashes(root) == before


def test_reference_only_reads_configured_root(
    corpus: tuple[Path, dict[str, UUID]], tmp_path: Path
) -> None:
    import hashlib

    from kipartmanager.domain.kicad import KiCadReference, LibraryRoots
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex

    root, _ = corpus
    library = tmp_path / "external"
    library.mkdir()
    file = library / "Synthetic.kicad_sym"
    file.write_bytes((FIXTURES / "Synthetic.kicad_sym").read_bytes())
    LocalKiCadIndex(root).configure(LibraryRoots(symbols=str(library)))
    ref = KiCadReference(
        asset_type=AssetType.SYMBOL,
        library="Synthetic",
        name="Simple",
        relative_path=file.name,
        sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
    )
    before = hashes(tmp_path)
    assert ReadonlyPreviews(root).official(ref).drawings[0].name == "Simple"
    assert hashes(tmp_path) == before
    file.unlink()
    with pytest.raises(PreviewProblem, match="introuvable"):
        ReadonlyPreviews(root).official(ref)


def test_back_copper_is_not_mislabelled_front_copper() -> None:
    from kipartmanager.infrastructure.kicad_preview import drawings

    data = (FIXTURES / "DIP8.kicad_mod").read_text().replace('"F.Cu"', '"B.Cu"')
    result = drawings(data, AssetType.FOOTPRINT)[0]
    assert not any(p.layer in {"Pads", "Pad1"} for p in result.primitives)
    assert any("hors cuivre avant" in warning for warning in result.warnings)
