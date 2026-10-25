"""TECH-01: open only an explicit, frozen test copy. No bootstrap or migrations."""

import json
import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool

from kipartmanager.domain.entities import DomainError

SCHEMA = "0007_asset_provenance"
COMPATIBLE_SCHEMAS = {SCHEMA, "0008_ingestion_operations"}
COPY_FORMAT = "fabparts-tech01-copy/1"


def open_copy(data_dir: Path) -> Engine:
    root = data_dir.resolve(strict=True)
    try:
        marker = json.loads((root / "TECH01_COPY.json").read_text())
        source = Path(marker["source"]).resolve()
        if marker["format"] != COPY_FORMAT or root == source or root.is_relative_to(source):
            raise ValueError("Not an isolated copy")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DomainError("Une copie TECH-01 explicite et isolée est requise.") from error
    database = root / "database" / "catalogue.sqlite3"
    if (
        database.is_symlink()
        or not database.is_file()
        or not database.resolve().is_relative_to(root)
    ):
        raise DomainError("Base de la copie absente ou externe.")
    if any(database.with_name(database.name + suffix).exists() for suffix in ("-wal", "-journal")):
        raise DomainError("La copie doit être figée, sans journal SQLite actif.")

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.execute("PRAGMA query_only=ON")
        # Deny writes/DDL/ATTACH even if a repository accidentally exposes a mutator.
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_TRANSACTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        connection.set_authorizer(
            lambda action, _a, _b, _db, _trigger: (
                sqlite3.SQLITE_OK
                if (
                    action in allowed
                    or (action == sqlite3.SQLITE_PRAGMA and _a == "read_uncommitted" and _b is None)
                )
                else sqlite3.SQLITE_DENY
            )
        )
        return connection

    engine = create_engine("sqlite://", creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if version not in COMPATIBLE_SCHEMAS:
                raise DomainError("Schéma incompatible ; aucune migration n’a été exécutée.")
    except Exception:
        engine.dispose()
        raise
    return engine
