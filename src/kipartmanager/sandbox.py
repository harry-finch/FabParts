"""Prepare a NEW disposable TECH-03 sandbox; never convert an existing catalogue."""

import argparse
from pathlib import Path

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.ingestion_sandbox import prepare_database, restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", type=Path, required=True)
    parser.add_argument("--restore-from", type=Path)
    args = parser.parse_args()
    engine = (
        restore_backup(args.restore_from, args.create)
        if args.restore_from
        else prepare_database(args.create)
    )
    try:
        Catalogue(SqliteCatalogue(engine)).initialize_defaults()
    finally:
        engine.dispose()
    print("Sandbox TECH-03 préparé ; données de test uniquement.")


if __name__ == "__main__":
    main()
