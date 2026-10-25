"""Explicit disposable writable roots, exclusive ownership and retained backups."""

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.database import create_database_engine, migrate

SANDBOX_FORMAT = "fabparts-tech03-sandbox/1"
SCHEMA = "0008_ingestion_operations"


def checked_root(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    resolved = absolute.resolve()
    # No symbolic component, including a root redirected onto personal data.
    if absolute != resolved:
        raise DomainError("Le sandbox doit utiliser un chemin sans lien symbolique.")
    production = (Path.home() / "Library/Application Support/KiPart Manager").resolve()
    if resolved == production or production in resolved.parents or resolved in production.parents:
        raise DomainError("Le catalogue personnel ne peut pas devenir un sandbox.")
    if (resolved / "TECH01_COPY.json").exists():
        raise DomainError("Une copie readonly ne peut pas devenir un sandbox writable.")
    return resolved


def check_tree(root: Path) -> None:
    links: dict[tuple[int, int], tuple[int, int]] = {}
    for path in root.rglob("*"):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (
            stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
        ):
            raise DomainError("Lien ou fichier spécial interdit dans le sandbox.")
        if stat.S_ISREG(info.st_mode):
            key = (info.st_dev, info.st_ino)
            links[key] = (links.get(key, (0, 0))[0] + 1, info.st_nlink)
    # AssetStore publishes by link, then removes staging. A crash between the two
    # operations leaves two INTERNAL names; it must not prevent safe recovery.
    if any(count != total for count, total in links.values()):
        raise DomainError("Lien physique vers un fichier extérieur au sandbox interdit.")


def prepare_database(path: Path) -> Engine:
    root = checked_root(path)
    if root.exists():
        raise DomainError("Préparer un dossier neuf ; aucun catalogue existant n’est remplacé.")
    root.mkdir(parents=True, mode=0o700)
    for name in ("assets", "config", "preparations", "backups"):
        (root / name).mkdir(mode=0o700)
    engine = create_database_engine(root / "database/catalogue.sqlite3")
    try:
        migrate(engine)
        (root / "TECH03_SANDBOX.json").write_text(
            json.dumps(
                {
                    "format": SANDBOX_FORMAT,
                    "id": str(uuid4()),
                }
            )
        )
    except Exception:
        engine.dispose()
        raise
    return engine


def restore_backup(backup: Path, destination: Path) -> Engine:
    """Shared sealed backup recovery into a NEW sandbox, retaining its source."""
    from kipartmanager.infrastructure.workspace_backup import (
        atomic_json,
        restore_files,
        verify_backup,
    )

    if verify_backup(backup)["schema"] != SCHEMA:
        raise DomainError("Sauvegarde incompatible avec le sandbox.")
    root = checked_root(destination)
    if root.exists():
        raise DomainError("Restaurer dans un dossier neuf.")
    root.mkdir(parents=True, mode=0o700)
    restore_files(backup, root)
    for name in ("preparations", "backups"):
        (root / name).mkdir(mode=0o700)
    atomic_json(root / "TECH03_SANDBOX.json", {"format": SANDBOX_FORMAT, "id": str(uuid4())})
    return create_database_engine(root / "database/catalogue.sqlite3")


def exclusive_lock(path: Path) -> BinaryIO:
    if os.name != "posix":
        raise DomainError("Verrou POSIX requis / POSIX lock required")
    import fcntl

    lock = path.open("a+b")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise DomainError("Espace déjà ouvert / Workspace already open") from error
    return lock


@dataclass
class WritableSandbox:
    root: Path
    engine: Engine
    lock: BinaryIO
    backup: Path

    def close(self) -> None:
        self.engine.dispose()
        self.lock.close()


def open_sandbox(path: Path) -> WritableSandbox:
    root = checked_root(path)
    try:
        marker = json.loads((root / "TECH03_SANDBOX.json").read_text())
        if marker["format"] != SANDBOX_FORMAT:
            raise ValueError
        UUID(marker["id"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DomainError("Un sandbox TECH-03 explicitement préparé est requis.") from error
    check_tree(root)
    lock = exclusive_lock(root / ".writer.lock")
    engine: Engine | None = None
    try:
        db = root / "database/catalogue.sqlite3"
        if not db.is_file():
            raise DomainError("Base du sandbox absente.")
        engine = create_database_engine(db)
        with engine.connect() as connection:
            if connection.scalar(text("SELECT version_num FROM alembic_version")) != SCHEMA:
                raise DomainError("Schéma sandbox incompatible ; aucune migration automatique.")
            if connection.exec_driver_sql("PRAGMA quick_check").scalar() != "ok":
                raise DomainError("Intégrité du sandbox invalide.")
        from kipartmanager.infrastructure.workspace_backup import create_backup

        backup = create_backup(root, root / "backups")
        # Root ownership is exclusive; only explicitly named preparation directories are ours.
        for folder in (root / "preparations").iterdir():
            if (
                folder.is_dir()
                and len(folder.name) == 48
                and all(c in "0123456789abcdef" for c in folder.name)
            ):
                shutil.rmtree(folder)
        return WritableSandbox(root, engine, lock, backup)
    except BlockingIOError as error:
        lock.close()
        raise DomainError("Ce sandbox est déjà ouvert en écriture.") from error
    except Exception:
        if engine is not None:
            engine.dispose()
        lock.close()
        raise
