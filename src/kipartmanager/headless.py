"""TECH-01 composition root. Run with --data-dir pointing to a frozen test copy."""

import argparse
import sys
from pathlib import Path

from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.headless_ipc import serve
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.readonly_catalogue import open_copy
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        engine = open_copy(arguments.data_dir)
    except Exception as error:
        print(f"TECH-01 startup refused: {error}", file=sys.stderr, flush=True)
        return 2
    try:
        repository = SqliteCatalogue(engine)
        reader = CatalogueReader(Catalogue(repository), repository, SqliteDocumentation(engine))
        previews = AssetPreviews(reader, ReadonlyPreviews(arguments.data_dir))
        try:
            serve(reader, sys.stdin.buffer, sys.stdout.buffer, previews)
        finally:
            previews.clear()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
