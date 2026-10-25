"""TECH-02B transport, geometry, real optional CAD and cancellation regression tests."""

import base64
import hashlib
import os
import struct
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.model_jobs import ModelJobs
from kipartmanager.domain.entities import DomainError, Package, Part
from kipartmanager.headless_ipc import MAX_RESPONSE, respond
from kipartmanager.infrastructure import model_preview as model
from kipartmanager.infrastructure.mesh_geometry import encode_mesh
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews
from kipartmanager.ports.previews import PDF_LIMIT, Mesh, PreviewProblem
from tests.model_preview_corpus import FIXTURES, create_model_corpus
from tests.test_headless import hashes, reader_for, request


def ready(jobs: ModelJobs, handle: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = jobs.status(handle)
        if result["status"] != "loading":
            return result
        time.sleep(0.005)
    pytest.fail("3D worker did not complete")


@pytest.mark.parametrize(
    "name,vertices,triangles,bounds",
    [
        ("box.wrl", 8, 12, [[7, -7, 2], [17, -1, 4]]),
        ("package.wrl", 72, 108, [[7, -8.5, 0], [17, 0.5, 4]]),
    ],
)
def test_original_wrl_bounds_materials_and_binary(
    name: str, vertices: int, triangles: int, bounds: list[list[float]]
) -> None:
    content = (FIXTURES / name).read_bytes()
    binary, meta = model.convert_mesh(content, threading.Event())
    assert struct.unpack_from("<4sII", binary) == (b"FPM1", vertices, triangles)
    assert len(binary) == 12 + vertices * 24 + triangles * 25
    assert meta["bounds"] == bounds and meta["units"] == "source"
    assert not meta["warnings"]
    if name == "package.wrl":
        assert len(set(model.wrl_mesh(content).colors)) == 2
    assert (FIXTURES / name).read_bytes() == content


@pytest.mark.parametrize(
    "points,face",
    [
        (((0, 0, 0), (2, 0, 0), (1, 0.5, 0), (2, 2, 0), (0, 2, 0)), (0, 1, 2, 3, 4)),
        (((0, 0, 0), (2, 2, 0), (0, 2, 0), (2, 0, 0)), (0, 1, 2, 3)),
        (((0, 0, 0), (1, 0, 0), (1, 1, 0.1), (0, 1, 0)), (0, 1, 2, 3)),
        (((0, 0, 0), (1, 0, 0), (2, 0, 0)), (0, 1, 2)),
        (((0, 0, 0), (1, 0, 0), (0, 1, 0)), (0, 1, 2, 0)),
    ],
)
def test_no_silent_concave_nonplanar_or_degenerate_surface(points: Any, face: Any) -> None:
    with pytest.raises(PreviewProblem):
        encode_mesh(Mesh(points, (face,), ((0.2, 0.4, 0.6),)), threading.Event())


def test_winding_double_sides_collinear_and_complexity() -> None:
    source = (FIXTURES / "box.wrl").read_bytes()
    regular = model.wrl_mesh(source)
    reverse = model.wrl_mesh(
        source.replace(b"IndexedFaceSet {", b"IndexedFaceSet {ccw FALSE solid FALSE")
    )
    assert reverse.faces == tuple(tuple(reversed(face)) for face in regular.faces)
    payload, meta = encode_mesh(reverse, threading.Event())
    assert payload[-int(meta["triangles"]) :] == b"\1" * 12
    polygon = Mesh(
        ((0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)),
        ((0, 1, 2, 3, 4),),
        ((0.2, 0.3, 0.4),),
    )
    assert encode_mesh(polygon, threading.Event())[1]["triangles"] == 2
    with pytest.raises(PreviewProblem, match="complexes"):
        encode_mesh(replace(polygon, faces=(tuple(range(1500)),)), threading.Event())
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(PreviewProblem, match="annulée"):
        model.convert_mesh(source, cancelled)
    with pytest.raises(PreviewProblem, match="16 Mio"):
        model.convert_mesh(b"x" * (PDF_LIMIT + 1), threading.Event())


def test_model_business_resolution_chunks_and_no_writes(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    ids = create_model_corpus(root)
    before = hashes(root)
    engine, reader = reader_for(root)
    jobs = ModelJobs(model.convert_mesh)
    previews = AssetPreviews(reader, ReadonlyPreviews(root), jobs)
    try:
        initial = previews.get(str(ids["01 Simple DIP"]), "MODEL_3D")
        assert initial["status"] == "loading" and initial["selected"]
        result = ready(jobs, initial["handle"])
        assert result["status"] == "ready"
        block = jobs.chunk(initial["handle"], 0)
        payload = base64.b64decode(str(block["data"]))
        assert len(str(block)) < MAX_RESPONSE and block["eof"]
        assert hashlib.sha256(payload).hexdigest() == result["mesh_sha256"]
        assert previews.get(str(ids["05 Passive SMD"]), "MODEL_3D")["status"] == "missing"
        assert previews.get(str(ids["09 Empty resources"]), "MODEL_3D")["status"] == "absent"
        part = reader.catalogue.require(Part, ids["02 Four sides SOIC"])
        assert part.package_id
        package = reader.catalogue.require(Package, part.package_id)
        foreign = str(package.asset_ids[-1])
        assert (
            previews.get(str(ids["01 Simple DIP"]), "MODEL_3D", foreign)["status"] == "inaccessible"
        )
        jobs.release(initial["handle"])
        with pytest.raises(DomainError):
            jobs.chunk(initial["handle"], 0)
        for method in ("get_model_status", "read_mesh_chunk", "release_model_preview"):
            bad = respond(request(method, {"handle": "../model", "path": "no"}), reader, previews)
            assert not bad["ok"] and bad["error"]["code"] == "INVALID_PARAMS"
        assert hashes(root) == before
    finally:
        previews.clear()
        engine.dispose()


def test_jobs_nonblocking_release_out_of_order_expiry_and_close() -> None:
    entered = threading.Event()

    def slow(source: bytes, cancel: threading.Event) -> tuple[bytes, dict[str, Any]]:
        entered.set()
        cancel.wait(4)
        return b"late", {}

    jobs = ModelJobs(slow)
    h1 = jobs.start(b"1")
    assert entered.wait(1)
    h2 = jobs.start(b"2")
    assert jobs.status(h1)["status"] == "loading"
    jobs.release(h2)
    h3 = jobs.start(b"3")
    assert list(jobs.jobs) == [h1, h3]
    jobs.jobs[h1].expires = 0
    with pytest.raises(DomainError, match="expirée"):
        jobs.status(h1)
    assert list(jobs.jobs) == [h3]
    started = time.monotonic()
    jobs.close()
    assert time.monotonic() - started < 1 and not jobs.jobs and not jobs.buffers.handles
    assert jobs.worker and not jobs.worker.is_alive()
    with pytest.raises(DomainError, match="arrêté"):
        jobs.start(b"no")


def test_bounded_worker_failures_do_not_kill_following_jobs() -> None:
    def convert(source: bytes, cancel: threading.Event) -> tuple[bytes, dict[str, Any]]:
        if source == b"large":
            return b"x" * (PDF_LIMIT + 1), {}
        if source == b"crash":
            raise RuntimeError("private path must not leak")
        return model.convert_mesh((FIXTURES / "box.wrl").read_bytes(), cancel)

    jobs = ModelJobs(convert)
    try:
        assert ready(jobs, jobs.start(b"large"))["status"] == "too_large"
        assert ready(jobs, jobs.start(b"crash")) == {
            "status": "error",
            "message": "Conversion 3D échouée.",
            "handle": next(reversed(jobs.jobs)),
        }
        assert ready(jobs, jobs.start(b"okay"))["status"] == "ready"
        assert len(jobs.jobs) == 2
    finally:
        jobs.close()


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_external_converter_is_terminated_and_temp_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    marker = tmp_path / "started"
    script = tmp_path / "converter"
    script.write_text(
        f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(str(os.getpid())+'\\n'+os.getcwd())\n"
        "time.sleep(10)\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("KIPART_FREECAD_CMD", str(script))
    cancel = threading.Event()
    errors = []

    def run() -> None:
        try:
            model.step_mesh(b"ISO-10303-21; test", cancel)
        except DomainError as error:
            errors.append(str(error))

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 2
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.exists()
    pid, folder = marker.read_text().splitlines()
    if mode == "cancel":
        cancel.set()
    else:
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 31)
    worker.join(2)
    assert not worker.is_alive() and errors
    assert not Path(folder).exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid), 0)


@pytest.mark.skipif(
    os.environ.get("FABPARTS_TEST_FREECAD") != "1",
    reason="requires explicitly enabled real FreeCAD",
)
@pytest.mark.parametrize(
    "name,expected",
    [
        ("box", [[7, -7, 2], [17, -1, 4]]),
        ("package", [[7, -8.5, 0], [17, 0.5, 4]]),
        ("details", [[0, 0, 0], [8, 8, 1]]),
    ],
)
def test_real_freecad_dimensions_and_units(name: str, expected: list[list[float]]) -> None:
    binary, meta = model.convert_mesh((FIXTURES / (name + ".step")).read_bytes(), threading.Event())
    assert meta["bounds"] == expected and meta["units"] == "mm"
    assert binary.startswith(b"FPM1") and meta["warnings"]


def test_mesh_larger_than_json_frame_is_transferred_in_verified_chunks() -> None:
    vertices = tuple(
        p
        for i in range(15000)
        for p in ((i, 0, 0), (i + 0.4, 0, 0), (i + 0.4, 0.4, 0), (i, 0.4, 0))
    )
    mesh = Mesh(
        vertices,
        tuple(tuple(range(i, i + 4)) for i in range(0, 60000, 4)),
        ((0.2, 0.4, 0.6),) * 15000,
    )
    payload, meta = encode_mesh(mesh, threading.Event())
    assert len(payload) > MAX_RESPONSE

    def converter(source: bytes, cancel: threading.Event) -> tuple[bytes, dict[str, Any]]:
        return payload, meta

    jobs = ModelJobs(converter)
    try:
        handle = jobs.start(b"synthetic mesh")
        result = ready(jobs, handle)
        chunks = []
        for offset in range(0, result["size_bytes"], 65536):
            chunk = jobs.chunk(handle, offset)
            assert len(str(chunk)) < 90000 and chunk["offset"] == offset
            chunks.append(base64.b64decode(str(chunk["data"])))
        assert b"".join(chunks) == payload
        assert hashlib.sha256(payload).hexdigest() == result["mesh_sha256"]
        assert chunk["eof"]
        jobs.release(handle)
        assert not jobs.buffers.handles
    finally:
        jobs.close()
