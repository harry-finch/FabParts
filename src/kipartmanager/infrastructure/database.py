"""Local SQLite setup and packaged Alembic migrations."""

import sqlite3
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event


def create_database_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)))

    def enable_foreign_keys(connection: sqlite3.Connection, record: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", enable_foreign_keys)
    return engine


def migrate(engine: Engine, revision: str = "head", *, downgrade: bool = False) -> None:
    # Only controlled personal-workspace initialization/upgrades and administration migrate.
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    with engine.begin() as connection:
        # sqlite3 legacy mode does not start a transaction for DDL. Start one
        # explicitly so a later downgrade refusal cannot leave a partial schema.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["connection"] = connection
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
