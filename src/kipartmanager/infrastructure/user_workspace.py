"""Personal host-owned workspace composition; no legacy catalogue discovery/import."""

import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import Engine

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.ingestion_sandbox import (
    SCHEMA,
    checked_root,
    prepare_database,
)
from kipartmanager.infrastructure.ingestion_sandbox import (
    exclusive_lock as exclusive,
)
from kipartmanager.infrastructure.workspace_backup import (
    atomic_json,
    checked_directory,
    create_backup,
    database_schema,
    digest,
    restore_files,
    sync_dir,
    verify_backup,
)

HOME_FORMAT = "fabparts-user-home/1"
WORKSPACE_FORMAT = "fabparts-user-workspace/1"


def default_home() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/FabParts"
    if sys.platform.startswith("linux"):
        return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "FabParts"
    raise DomainError("Plateforme non qualifiée / Platform not qualified")


def mark_workspace(root: Path, identity: str) -> None:
    atomic_json(root / "FABPARTS_WORKSPACE.json", {"format": WORKSPACE_FORMAT, "id": identity})


def check_workspace(root: Path, identity: str) -> None:
    checked_root(root)
    checked_directory(root)
    try:
        marker = json.loads((root / "FABPARTS_WORKSPACE.json").read_text())
        if marker != {"format": WORKSPACE_FORMAT, "id": identity}:
            raise ValueError
        if (root / "TECH03_SANDBOX.json").exists():
            raise ValueError
    except (OSError, ValueError) as error:
        raise DomainError("Workspace personnel non reconnu / Invalid personal workspace") from error


def upgrade(root: Path, backups: Path) -> Path | None:
    schema = database_schema(root / "database/catalogue.sqlite3")
    if schema == SCHEMA:
        return None
    # The only qualified upgrade is the existing additive 0007 -> 0008 migration.
    if schema != "0007_asset_provenance":
        raise DomainError("Migration incompatible / Unsupported migration")
    backup = create_backup(root, backups)
    verify_backup(backup)
    engine = create_database_engine(root / "database/catalogue.sqlite3")
    try:
        migrate(engine, SCHEMA)
    finally:
        engine.dispose()
    if database_schema(root / "database/catalogue.sqlite3") != SCHEMA:
        raise DomainError("Migration incomplète / Incomplete migration")
    return backup


@dataclass
class UserWorkspace:
    home: Path
    root: Path
    engine: Engine
    lock: BinaryIO
    requires_restart: bool = False
    selected: dict[str, tuple[Path, str]] = field(default_factory=dict)

    def close(self) -> None:
        self.engine.dispose()
        self.lock.close()

    def info(self) -> dict[str, Any]:
        return {
            "mode": "personal",
            "path": str(self.root),
            "backups": str(self.home / "backups"),
            "restart_required": self.requires_restart,
            "schema": SCHEMA,
        }

    def backup(self) -> dict[str, Any]:
        if self.requires_restart:
            raise DomainError("Redémarrage requis / Restart required")
        path = create_backup(self.root, self.home / "backups")
        return {"path": str(path), "files": len(verify_backup(path)["files"])}

    def verify(self, source: Path) -> dict[str, Any]:
        manifest = verify_backup(source)
        handle = secrets.token_hex(24)
        self.selected.clear()
        self.selected[handle] = (source.absolute(), digest(source / "manifest.json"))
        return {
            "handle": handle,
            "files": len(manifest["files"]),
            "schema": manifest["schema"],
            "created_at": manifest["created_at"],
        }

    def restore(self, handle: str) -> dict[str, Any]:
        if self.requires_restart:
            raise DomainError("Redémarrage requis / Restart required")
        if handle not in self.selected:
            raise DomainError("Sauvegarde non sélectionnée / Backup not selected")
        source, expected = self.selected[handle]
        if digest(source / "manifest.json") != expected:
            raise DomainError("Sauvegarde modifiée / Backup changed")
        verify_backup(source)
        retained = self.backup()["path"]
        identity = uuid4().hex
        temporary = self.home / "workspaces" / (".restoring-" + identity)
        final = temporary.with_name(identity)
        temporary.mkdir(mode=0o700)
        restore_files(source, temporary)
        for name in ("preparations",):
            (temporary / name).mkdir(mode=0o700)
        mark_workspace(temporary, identity)
        upgrade(temporary, self.home / "backups")
        check_workspace(temporary, identity)
        if database_schema(temporary / "database/catalogue.sqlite3") != SCHEMA:
            raise DomainError("Restauration incompatible / Incompatible restore")
        temporary.rename(final)
        sync_dir(final.parent)
        atomic_json(self.home / "active.json", {"workspace": identity})
        self.requires_restart = True
        self.selected.clear()
        return {"restart_required": True, "path": str(final), "retained_backup": retained}


def open_personal(
    path: Path | None = None, *, initialize: Callable[[Engine], None]
) -> UserWorkspace:
    home = checked_root(path or default_home())
    if home.exists():
        checked_directory(home)
        if not (home / "USER_HOME.json").is_file() and not tuple(home.iterdir()):
            atomic_json(home / "USER_HOME.json", {"format": HOME_FORMAT})
        if not (home / "USER_HOME.json").is_file():
            raise DomainError("Dossier personnel non reconnu / Unrecognized user folder")
    else:
        home.mkdir(parents=True, mode=0o700)
        atomic_json(home / "USER_HOME.json", {"format": HOME_FORMAT})
    try:
        if json.loads((home / "USER_HOME.json").read_text()) != {"format": HOME_FORMAT}:
            raise DomainError("Marqueur personnel incompatible / Invalid user marker")
    except (OSError, ValueError) as error:
        raise DomainError("Marqueur personnel illisible / Invalid user marker") from error
    if not os.access(home, os.R_OK | os.W_OK | os.X_OK) or not home.stat().st_mode & 0o222:
        raise DomainError("Espace personnel inaccessible / Workspace not writable")
    lock = exclusive(home / ".writer.lock")
    engine: Engine | None = None
    try:
        (home / "workspaces").mkdir(exist_ok=True, mode=0o700)
        (home / "backups").mkdir(exist_ok=True, mode=0o700)
        pointer = home / "active.json"
        if not pointer.exists():
            identity = uuid4().hex
            temporary = home / "workspaces" / (".creating-" + identity)
            engine = prepare_database(temporary)
            initialize(engine)
            engine.dispose()
            engine = None
            (temporary / "TECH03_SANDBOX.json").unlink()
            mark_workspace(temporary, identity)
            temporary.rename(temporary.with_name(identity))
            sync_dir(temporary.parent)
            atomic_json(pointer, {"workspace": identity})
        try:
            identity = json.loads(pointer.read_text())["workspace"]
            if UUID(identity).hex != identity:
                raise ValueError
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise DomainError("Workspace actif invalide / Invalid active workspace") from error
        root = home / "workspaces" / identity
        check_workspace(root, identity)
        upgrade(root, home / "backups")
        for name in ("assets", "config", "database", "publications", "preparations"):
            folder = root / name
            folder.mkdir(exist_ok=True, mode=0o700)
            probe = folder / (".permissions-" + uuid4().hex)
            try:
                with probe.open("xb") as stream:
                    stream.write(b"permission check")
            finally:
                probe.unlink(missing_ok=True)
        engine = create_database_engine(root / "database/catalogue.sqlite3")
        # Same transient cleanup as TECH-03, while owning the home exclusively.
        for folder in (root / "preparations").iterdir():
            if (
                folder.is_dir()
                and len(folder.name) == 48
                and all(c in "0123456789abcdef" for c in folder.name)
            ):
                import shutil

                shutil.rmtree(folder)
        return UserWorkspace(home, root, engine, lock)
    except Exception:
        if engine is not None:
            engine.dispose()
        lock.close()
        raise
