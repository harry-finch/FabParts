"""Complete, sealed snapshots shared by sandbox and personal workspace recovery."""

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.ingestion_sandbox import SCHEMA, check_tree

FORMAT = "fabparts-backup/1"
SUPPORTED = {"0007_asset_provenance", SCHEMA}
DATA_DIRS = ("assets", "config", "publications")
KNOWN = {
    *DATA_DIRS,
    "database",
    "index",
    "preparations",
    "backups",
    ".writer.lock",
    "TECH03_SANDBOX.json",
    "FABPARTS_WORKSPACE.json",
}


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name("." + path.name + "-" + uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    sync_dir(path.parent)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def database_schema(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise DomainError("Base absente / Missing database")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT version_num FROM alembic_version").fetchall()
            if len(rows) != 1 or rows[0][0] not in SUPPORTED:
                raise DomainError("Schéma incompatible / Unsupported schema")
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise DomainError("SQLite corrompu / Corrupt SQLite")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise DomainError("Clés étrangères invalides / Invalid foreign keys")
            return str(rows[0][0])
    except sqlite3.Error as error:
        raise DomainError("SQLite incompatible ou corrompu / Invalid SQLite") from error


def checked_directory(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if absolute != absolute.resolve() or not absolute.is_dir():
        raise DomainError("Dossier absent ou lié / Missing or linked directory")
    check_tree(absolute)
    return absolute


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    return {
        p.relative_to(root).as_posix(): {"sha256": digest(p), "size": p.stat().st_size}
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).as_posix() != "manifest.json"
    }


def check_authority(root: Path, database: Path) -> None:
    # SQLite references must have corresponding canonical bytes, not merely valid FKs.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        for sha, size in db.execute("SELECT sha256,size_bytes FROM asset_files"):
            file = root / "assets/blobs" / sha[:2] / sha
            if not file.is_file() or file.stat().st_size != size or digest(file) != sha:
                raise DomainError("Asset canonique absent ou altéré / Missing or changed asset")
    from kipartmanager.infrastructure.asset_store import LocalAssetStore
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications

    publications = LocalPublications(
        root / "publications",
        LocalLibraryBuilder(LocalAssetStore(root / "assets"), LocalKiCadIndex(root), root),
    )
    for publication in publications.list_publications():
        publications.verify(publication)


def verify_backup(path: Path, *, preparing: bool = False) -> dict[str, Any]:
    root = checked_directory(path)
    if root.name.startswith(".partial-") and not preparing:
        raise DomainError("Sauvegarde interrompue / Incomplete backup")
    try:
        manifest_path = root / "manifest.json"
        if manifest_path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("manifest size")
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["format"] != FORMAT
            or manifest["schema"] not in SUPPORTED
            or not isinstance(manifest["files"], dict)
        ):
            raise ValueError("format")
        for name, record in manifest["files"].items():
            relative = PurePosixPath(name)
            if (
                not name
                or "\\" in name
                or relative.is_absolute()
                or ".." in relative.parts
                or name != relative.as_posix()
                or not isinstance(record, dict)
                or not (name == "catalogue.sqlite3" or relative.parts[0] in DATA_DIRS)
            ):
                raise ValueError("path")
        if inventory(root) != manifest["files"]:
            raise ValueError("hash or unlisted file")
        if database_schema(root / "catalogue.sqlite3") != manifest["schema"]:
            raise ValueError("schema")
        check_authority(root, root / "catalogue.sqlite3")
        for folder in DATA_DIRS:
            if not (root / folder).is_dir():
                raise ValueError("missing directory")
        return dict(manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DomainError("Sauvegarde incomplète ou altérée / Invalid backup") from error


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    before = source.stat()
    with source.open("rb") as src, target.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    after = source.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise DomainError("Fichier modifié pendant la copie / File changed during copy")


def copy_tree(source: Path, target: Path) -> None:
    target.mkdir(mode=0o700)
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            # Interrupted Asset Store imports are transient, not canonical data.
            if ".staging" in path.relative_to(source).parts:
                continue
            dest = target / path.relative_to(source)
            if path.is_dir():
                dest.mkdir(exist_ok=True, mode=0o700)
            else:
                copy_file(path, dest)


def create_backup(root: Path, destination: Path) -> Path:
    checked_directory(root)
    if any(p.name not in KNOWN for p in root.iterdir()):
        raise DomainError("Contenu persistant non inventorié / Unknown persistent content")
    schema = database_schema(root / "database/catalogue.sqlite3")
    if any(
        p.name
        not in {
            "catalogue.sqlite3",
            "catalogue.sqlite3-wal",
            "catalogue.sqlite3-shm",
            "catalogue.sqlite3-journal",
        }
        for p in (root / "database").iterdir()
    ):
        raise DomainError("Base supplémentaire non inventoriée / Unknown database file")
    check_authority(root, root / "database/catalogue.sqlite3")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.absolute() != destination.resolve():
        raise DomainError("Destination liée / Linked destination")
    identity = uuid4().hex
    temporary, final = destination / (".partial-" + identity), destination / identity
    temporary.mkdir(mode=0o700)
    with closing(
        sqlite3.connect((root / "database/catalogue.sqlite3").as_uri() + "?mode=ro", uri=True)
    ) as src:
        with closing(sqlite3.connect(temporary / "catalogue.sqlite3")) as dst:
            src.backup(dst)
    with (temporary / "catalogue.sqlite3").open("rb") as file:
        os.fsync(file.fileno())
    for name in DATA_DIRS:
        copy_tree(root / name, temporary / name)
    atomic_json(
        temporary / "manifest.json",
        {
            "format": FORMAT,
            "schema": schema,
            "created_at": datetime.now(UTC).isoformat(),
            "files": inventory(temporary),
        },
    )
    verify_backup(temporary, preparing=True)
    temporary.rename(final)
    sync_dir(destination)
    return final


def restore_files(backup: Path, target: Path) -> dict[str, Any]:
    manifest = verify_backup(backup)
    copy_file(backup / "catalogue.sqlite3", target / "database/catalogue.sqlite3")
    for name in DATA_DIRS:
        copy_tree(backup / name, target / name)
    # Verify what was actually copied, including changes to the source during copy.
    actual = inventory(target)
    actual["catalogue.sqlite3"] = actual.pop("database/catalogue.sqlite3")
    if (
        actual != manifest["files"]
        or database_schema(target / "database/catalogue.sqlite3") != manifest["schema"]
    ):
        raise DomainError("Restauration altérée / Restored data mismatch")
    return manifest
