"""TECH-01 composition root. Run with --data-dir pointing to a frozen test copy."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.ingestion import Ingestion
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.model_jobs import ModelJobs
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.headless_ipc import serve
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.ingestion_sandbox import open_sandbox
from kipartmanager.infrastructure.ingestion_transactions import SqliteIngestionTransactions
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.model_preview import convert_mesh
from kipartmanager.infrastructure.prepared_files import LocalPreparedFiles
from kipartmanager.infrastructure.readonly_catalogue import open_copy
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--sandbox", action="store_true", help="Host-only prepared TECH-03 sandbox")
    arguments = parser.parse_args()
    sandbox = None
    try:
        sandbox = open_sandbox(arguments.data_dir) if arguments.sandbox else None
        engine = sandbox.engine if sandbox else open_copy(arguments.data_dir)
    except Exception as error:
        print(f"TECH-01 startup refused: {error}", file=sys.stderr, flush=True)
        return 2
    try:
        repository = SqliteCatalogue(engine)
        store = LocalAssetStore(arguments.data_dir / "assets") if sandbox else None
        catalogue = Catalogue(repository, store)
        documentation = SqliteDocumentation(engine)
        reader = CatalogueReader(catalogue, repository, documentation)
        previews = AssetPreviews(
            reader, ReadonlyPreviews(arguments.data_dir), ModelJobs(convert_mesh)
        )
        ingestion = None
        if sandbox and store:
            libraries = KiCadLibraries(LocalKiCadIndex(arguments.data_dir))
            ingestion = Ingestion(
                catalogue,
                documentation,
                LocalResolver(catalogue, repository, libraries),
                SqliteIngestionTransactions(engine),
                store,
                LocalPreparedFiles(arguments.data_dir, ReadonlyPreviews(arguments.data_dir)),
                previews,
                libraries,
            )
        with engine.connect() as connection:
            schema = str(connection.scalar(text("SELECT version_num FROM alembic_version")))
        try:
            serve(reader, sys.stdin.buffer, sys.stdout.buffer, previews, ingestion, schema)
        finally:
            previews.clear()
            if ingestion:
                ingestion.close()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        if sandbox:
            sandbox.close()
        else:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
