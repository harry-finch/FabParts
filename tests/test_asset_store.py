"""Managed-file integrity, atomic writes and failure behavior on disposable data."""

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from kipartmanager.domain.asset_files import AssetStoreError
from kipartmanager.infrastructure.asset_store import LocalAssetStore

FILES = {
    ".pdf": b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n",
    ".step": b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
    ".wrl": b"#VRML V2.0 utf8\nShape { geometry Box { size 1 1 1 } }\n",
    ".kicad_mod": (
        b'(footprint "M2_Test" (version 20260206) (generator "fixture") (layer "F.Cu"))\n'
    ),
    ".kicad_sym": (
        b'(kicad_symbol_lib (version 20251024) (generator "fixture") (symbol "M2_Test"))\n'
    ),
}


@pytest.mark.parametrize("extension", FILES)
def test_five_format_roundtrips(tmp_path: Path, extension: str) -> None:
    source = tmp_path / f"original{extension}"
    source.write_bytes(FILES[extension])
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    assert file.sha256 == hashlib.sha256(FILES[extension]).hexdigest()
    assert file.size_bytes == len(FILES[extension])
    assert file.original_name == source.name
    assert not Path(file.relative_key).is_absolute()
    store.verify(file)
    destination = tmp_path / f"copy{extension}"
    store.retrieve(file, str(destination))
    assert destination.read_bytes() == source.read_bytes() == FILES[extension]
    assert (store.root / file.relative_key).read_bytes() == FILES[extension]
    assert list((store.root / ".staging").iterdir()) == []


def test_case_insensitive_extension_and_step_alias(tmp_path: Path) -> None:
    source = tmp_path / "model.STP"
    source.write_bytes(FILES[".step"])
    file = LocalAssetStore(tmp_path / "assets").import_file(str(source))
    assert file.extension == ".stp"


def test_chunked_import_and_content_dedup(tmp_path: Path) -> None:
    data = b"payload" * 400_000
    source = tmp_path / "large.pdf"
    source.write_bytes(data)
    other = tmp_path / "other.pdf"
    other.write_bytes(data)
    store = LocalAssetStore(tmp_path / "assets")
    first, second = store.import_file(str(source)), store.import_file(str(other))
    assert first.sha256 == second.sha256 == hashlib.sha256(data).hexdigest()
    assert first.original_name != second.original_name
    assert len(list((store.root / "blobs").rglob(first.sha256))) == 1
    assert (store.root / first.relative_key).stat().st_ino != source.stat().st_ino
    source.write_bytes(b"source changed")
    store.verify(first)


@pytest.mark.parametrize("name,data", [("unknown.txt", b"data"), ("empty.pdf", b"")])
def test_unsupported_or_empty_input(tmp_path: Path, name: str, data: bytes) -> None:
    source = tmp_path / name
    source.write_bytes(data)
    with pytest.raises(ValueError):
        LocalAssetStore(tmp_path / "assets").import_file(str(source))
    assert list((tmp_path / "assets" / "blobs").glob("**/*")) == []


def test_missing_source(tmp_path: Path) -> None:
    with pytest.raises(AssetStoreError):
        LocalAssetStore(tmp_path / "assets").import_file(str(tmp_path / "missing.pdf"))


def test_corruption_or_missing_file_is_detected_and_never_replaced(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"original")
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    canonical = store.root / file.relative_key
    canonical.write_bytes(b"changed!")
    with pytest.raises(AssetStoreError):
        store.verify(file)
    with pytest.raises(AssetStoreError):
        store.import_file(str(source))
    destination = tmp_path / "copy.pdf"
    with pytest.raises(AssetStoreError):
        store.retrieve(file, str(destination))
    assert not destination.exists()
    assert canonical.read_bytes() == b"changed!"
    canonical.unlink()
    with pytest.raises(AssetStoreError):
        store.verify(file)


def test_retrieve_preserves_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source")
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    destination = tmp_path / "copy.pdf"
    destination.write_bytes(b"user data")
    with pytest.raises(AssetStoreError):
        store.retrieve(file, str(destination))
    assert destination.read_bytes() == b"user data"
    with pytest.raises(AssetStoreError):
        store.retrieve(file, str(store.root / "copy.pdf"))


def test_write_failure_does_not_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"data")
    store = LocalAssetStore(tmp_path / "assets")

    def denied(*args: object, **kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "link", denied)
    with pytest.raises(AssetStoreError):
        store.import_file(str(source))
    assert list((store.root / ".staging").iterdir()) == []
    assert list((store.root / "blobs").glob("*/*")) == []


def test_read_failure_and_bad_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"data")
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    with pytest.raises(AssetStoreError):
        store.verify(replace(file, size_bytes=file.size_bytes + 1))

    def denied(source: Path, destination: Path) -> tuple[str, int]:
        raise PermissionError("read denied")

    monkeypatch.setattr(LocalAssetStore, "_copy", staticmethod(denied))
    with pytest.raises(AssetStoreError):
        store.import_file(str(source))
    assert list((store.root / ".staging").iterdir()) == []


def test_canonical_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"data")
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    canonical = store.root / file.relative_key
    canonical.unlink()
    canonical.symlink_to(source)
    with pytest.raises(AssetStoreError):
        store.verify(file)
    assert source.read_bytes() == b"data"


def test_destination_appearing_during_retrieval_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"data")
    store = LocalAssetStore(tmp_path / "assets")
    file = store.import_file(str(source))
    destination = tmp_path / "copy.pdf"
    original_link = os.link

    def competing_write(source: Path, target: Path) -> None:
        target.write_bytes(b"other user data")
        original_link(source, target)

    monkeypatch.setattr(os, "link", competing_write)
    with pytest.raises(AssetStoreError):
        store.retrieve(file, str(destination))
    assert destination.read_bytes() == b"other user data"
    assert list(tmp_path.glob(".kipart-copy-*")) == []
