"""TECH-01 contracts, frozen-copy protection and Qt/network-free subprocess."""

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DatabaseError

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    DomainError,
    Package,
    Part,
)
from kipartmanager.headless_ipc import MAX_REQUEST, respond, serve
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.readonly_catalogue import open_copy


def hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def copy_data(tmp_path: Path, catalogue: Catalogue, engine: Engine) -> tuple[Path, Part]:
    package = Package(name="DIP-8")
    catalogue.save(package)
    asset = Asset(
        name="User symbol metadata", asset_type=AssetType.SYMBOL, origin=AssetOrigin.USER_PROVIDED
    )
    catalogue.save(asset)
    part = Part(name="NE555", description="Timer", package_id=package.id, asset_ids=(asset.id,))
    catalogue.save(part)
    catalogue.save(Part(name="Empty"))
    catalogue.save(Collection(name="Workshop", part_ids=(part.id,)))
    engine.dispose()
    (tmp_path / "TECH01_COPY.json").write_text(
        json.dumps(
            {
                "format": "fabparts-tech01-copy/1",
                "source": str(tmp_path.parent / "production"),
            }
        )
    )
    return tmp_path, part


def reader_for(path: Path) -> tuple[Engine, CatalogueReader]:
    engine = open_copy(path)
    repo = SqliteCatalogue(engine)
    return engine, CatalogueReader(Catalogue(repo), repo, SqliteDocumentation(engine))


def request(command: str, params: dict[str, Any] | None = None, **overrides: Any) -> bytes:
    data = {"protocol_version": 1, "request_id": "r1", "method": command, "params": params or {}}
    data.update(overrides)
    return json.dumps(data).encode() + b"\n"


def test_true_reads_and_no_writes(copy_data: tuple[Path, Part]) -> None:
    path, part = copy_data
    before = hashes(path)
    engine, reader = reader_for(path)
    try:
        libs = respond(request("list_libraries"), reader)["result"]
        assert {x["name"] for x in libs} == {"LabParts", "PersonalParts", "Workshop"}
        assert "Lab" not in {x["name"] for x in libs}
        page = respond(request("list_components", {"search": "ne555", "limit": 1}), reader)[
            "result"
        ]
        assert page["total"] == 1 and page["components"][0]["id"] == str(part.id)
        assert page["components"][0]["manufacturer"] == ""
        assert page["components"][0]["state"] == "DRAFT"
        assert page["components"][0]["package"]["name"] == "DIP-8"
        detail = respond(request("get_component", {"id": str(part.id)}), reader)["result"]
        assert detail["associated_assets"][0]["validation_state"] == "UNCHECKED"
        assert not detail["associated_assets"][0]["selected"]
        assert detail["qualification"] is None and not detail["preview_available"]
        empty = next(p for p in reader.catalogue.list_entities(Part) if p.name == "Empty")
        assert reader.component(empty.id)["associated_assets"] == []
        assert reader.components({"search": "no match"})["total"] == 0
        assert reader.components({"offset": 1, "limit": 1})["components"][0]["reference"] == "NE555"
        assert reader.components({"package": "DIP-8"})["total"] == 1
        assert reader.components({"state": "IDENTIFIED"})["total"] == 0
        library = next(x["id"] for x in libs if x["name"] == "Workshop")
        assert reader.components({"library": library})["total"] == 1
        with engine.connect() as connection:
            with pytest.raises(DatabaseError):
                connection.execute(text("UPDATE parts SET name='corrupted'"))
            with pytest.raises(DatabaseError):
                connection.execute(text("ATTACH ':memory:' AS other"))
    finally:
        engine.dispose()
    assert hashes(path) == before


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"{broken\n", "INVALID_JSON"),
        (b"[]\n", "INVALID_REQUEST"),
        (request("save_part"), "UNKNOWN_METHOD"),
        (request("health", {"shell": "whoami"}), "INVALID_PARAMS"),
        (request("health", protocol_version=2), "VERSION_MISMATCH"),
        (request("health", protocol_version=True), "VERSION_MISMATCH"),
        (request("health", request_id=""), "INVALID_REQUEST"),
        (request("health", method=["health"]), "INVALID_REQUEST"),
        (request("list_components", {"limit": 0}), "INVALID_PARAMS"),
        (request("list_components", {"limit": True}), "INVALID_PARAMS"),
        (request("list_components", {"limit": 101}), "INVALID_PARAMS"),
        (request("list_components", {"offset": -1}), "INVALID_PARAMS"),
        (request("list_components", {"state": "READY_FOR_PCB"}), "INVALID_PARAMS"),
        (request("list_components", {"library": "Lab"}), "INVALID_PARAMS"),
        (request("get_component", {"id": "wrong"}), "INVALID_PARAMS"),
        (request("get_component", {"id": str(uuid4())}), "DOMAIN_ERROR"),
    ],
)
def test_protocol_errors(copy_data: tuple[Path, Part], raw: bytes, code: str) -> None:
    engine, reader = reader_for(copy_data[0])
    try:
        response = respond(raw, reader)
        assert response["ok"] is False and response["error"]["code"] == code
        if code not in {"INVALID_JSON", "INVALID_REQUEST"}:
            assert response["request_id"] == "r1"
    finally:
        engine.dispose()


def test_frame_limit_and_shutdown(copy_data: tuple[Path, Part]) -> None:
    engine, reader = reader_for(copy_data[0])
    try:
        output = io.BytesIO()
        serve(reader, io.BytesIO(b"x" * (MAX_REQUEST + 1) + request("health")), output)
        assert json.loads(output.getvalue())["error"]["code"] == "FRAME_TOO_LARGE"
        output = io.BytesIO()
        serve(reader, io.BytesIO(request("shutdown") + request("health")), output)
        assert json.loads(output.getvalue())["result"] == {"stopping": True}
    finally:
        engine.dispose()


def test_headless_subprocess_without_qt_or_network(copy_data: tuple[Path, Part]) -> None:
    path, _ = copy_data
    before = hashes(path)
    script = """
import importlib.abc, sys, socket
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PySide6', 'shiboken6')): raise RuntimeError('Qt forbidden')
sys.meta_path.insert(0, NoQt())
def no_network(*args, **kwargs): raise RuntimeError('Network forbidden')
socket.socket.connect = no_network
socket.create_connection = no_network
from kipartmanager.headless import main
raise SystemExit(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, "--data-dir", str(path)],
        input=request("health") + request("list_libraries"),
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 2
    assert responses[0]["result"]["qt_loaded"] is False
    assert responses[0]["result"]["read_only"] is True
    assert hashes(path) == before


def test_copy_required_and_source_refused(copy_data: tuple[Path, Part]) -> None:
    path, _ = copy_data
    marker = path / "TECH01_COPY.json"
    marker.write_text(json.dumps({"format": "fabparts-tech01-copy/1", "source": str(path)}))
    with pytest.raises(DomainError):
        open_copy(path)
    marker.unlink()
    with pytest.raises(DomainError):
        open_copy(path)
