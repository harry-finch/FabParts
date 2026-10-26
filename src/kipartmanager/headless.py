"""FabParts composition root: explicit personal, sandbox or immutable-copy session."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import Engine, text

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
from kipartmanager.infrastructure.user_workspace import UserWorkspace, open_personal


def open_personal_workspace(path: Path | None = None) -> UserWorkspace:
    def initialize(engine: Engine) -> None:
        Catalogue(SqliteCatalogue(engine)).initialize_defaults()

    return open_personal(path, initialize=initialize)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--personal", action="store_true", help="Host-owned personal workspace")
    modes.add_argument("--sandbox", action="store_true", help="Host-only prepared TECH-03 sandbox")
    arguments = parser.parse_args()
    if not arguments.personal and arguments.data_dir is None:
        parser.error("--data-dir required for sandbox or readonly")
    sandbox = None
    personal = None
    try:
        sandbox = open_sandbox(arguments.data_dir) if arguments.sandbox else None
        personal = open_personal_workspace(arguments.data_dir) if arguments.personal else None
        engine = (
            personal.engine
            if personal
            else sandbox.engine
            if sandbox
            else open_copy(arguments.data_dir)
        )
        data_dir = personal.root if personal else arguments.data_dir
    except Exception as error:
        print(f"TECH-01 startup refused: {error}", file=sys.stderr, flush=True)
        return 2
    try:
        repository = SqliteCatalogue(engine)
        store = LocalAssetStore(data_dir / "assets") if sandbox or personal else None
        catalogue = Catalogue(repository, store)
        documentation = SqliteDocumentation(engine)
        reader = CatalogueReader(catalogue, repository, documentation)
        previews = AssetPreviews(reader, ReadonlyPreviews(data_dir), ModelJobs(convert_mesh))
        ingestion = None
        if (sandbox or personal) and store:
            libraries = KiCadLibraries(LocalKiCadIndex(data_dir))
            ingestion = Ingestion(
                catalogue,
                documentation,
                LocalResolver(catalogue, repository, libraries),
                SqliteIngestionTransactions(engine),
                store,
                LocalPreparedFiles(data_dir, ReadonlyPreviews(data_dir)),
                previews,
                libraries,
            )
        with engine.connect() as connection:
            schema = str(connection.scalar(text("SELECT version_num FROM alembic_version")))
        try:
            serve(
                reader, sys.stdin.buffer, sys.stdout.buffer, previews, ingestion, schema, personal
            )
        finally:
            previews.clear()
            if ingestion:
                ingestion.close()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        if personal:
            personal.close()
        elif sandbox:
            sandbox.close()
        else:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
