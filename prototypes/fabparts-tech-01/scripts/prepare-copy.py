"""Make a new private frozen copy. Refuse active journals; never open source writable.

Usage: python prepare-copy.py --source DATA --destination NEW_PRIVATE_DIRECTORY
The caller must keep the application closed during the copy. Nothing is overwritten.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


def hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    destination = args.destination.resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise SystemExit("Destination must be a new directory outside the source.")
    paths = list(source.rglob("*"))
    if any(p.is_symlink() or p.name.endswith(("-wal", "-journal")) for p in paths):
        raise SystemExit(
            "Close the application; active journals or symlinks require manual review."
        )
    before = hashes(source)
    shutil.copytree(source, destination)
    for database in source.rglob("*.sqlite3"):
        with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as src:
            with sqlite3.connect(destination / database.relative_to(source)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SystemExit("Copy rejected: SQLite integrity check failed.")
    if hashes(source) != before:
        raise SystemExit(
            "Copy rejected: source changed during snapshot. No acceptance marker written."
        )
    (destination / "TECH01_COPY.json").write_text(
        json.dumps(
            {
                "format": "fabparts-tech01-copy/1",
                "source": str(source),
                "source_sha256": before,
            },
            indent=2,
        )
    )
    # Keep the baseline outside the frozen copy, so it can verify every file inside it.
    destination.with_suffix(".sha256.json").write_text(json.dumps(hashes(destination), indent=2))
    print(f"Frozen copy created: {destination}")


if __name__ == "__main__":
    main()
