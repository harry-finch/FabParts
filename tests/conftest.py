"""Disposable migrated databases for local M1 tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(tmp_path / "database" / "catalogue.sqlite3")
    migrate(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def catalogue(engine: Engine) -> Catalogue:
    catalogue = Catalogue(SqliteCatalogue(engine))
    catalogue.initialize_defaults()
    return catalogue
