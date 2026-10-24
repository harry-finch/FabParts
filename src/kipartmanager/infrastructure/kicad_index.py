"""Read-only KiCad scanning and atomically replaceable SQLite cache."""

import hashlib
import json
import os
import sqlite3
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from kipartmanager.domain.entities import AssetType
from kipartmanager.domain.kicad import (
    IndexIssue,
    IndexReport,
    KiCadError,
    KiCadReference,
    LibraryRoots,
)
from kipartmanager.infrastructure.kicad_parser import check_version, parse, symbol_metadata

FIELDS = (
    "asset_type",
    "library",
    "name",
    "relative_path",
    "sha256",
    "description",
    "keywords",
    "format_version",
    "extends",
)
SCHEMA = 1


def discover_roots() -> LibraryRoots:
    """Environment overrides first, then standard locations; no KiCad execution."""
    common = [
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport"),
        Path.home() / "Applications/KiCad/KiCad.app/Contents/SharedSupport",
        Path("/usr/share/kicad"),
        Path("/usr/local/share/kicad"),
    ]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            common.extend(Path(base) / "KiCad" / str(v) / "share/kicad" for v in range(10, 5, -1))
    selected: list[str] = []
    for env_suffix, folder in (
        ("SYMBOL_DIR", "symbols"),
        ("FOOTPRINT_DIR", "footprints"),
        ("3DMODEL_DIR", "3dmodels"),
    ):
        candidates = [
            Path(value).expanduser()
            for version in range(10, 5, -1)
            if (value := os.environ.get(f"KICAD{version}_{env_suffix}"))
        ]
        candidates.extend(base / folder for base in common)
        selected.append(next((str(p.resolve()) for p in candidates if p.is_dir()), ""))
    return LibraryRoots(*selected)


class LocalKiCadIndex:
    def __init__(self, data_dir: Path) -> None:
        self.cache = data_dir / "index/kicad.sqlite3"
        self.config = data_dir / "config/kicad.toml"

    def discover(self) -> LibraryRoots:
        return discover_roots()

    def configuration(self) -> LibraryRoots:
        if not self.config.exists():
            return LibraryRoots()
        try:
            values = tomllib.loads(self.config.read_text(encoding="utf-8"))
            if set(values) != {"symbols", "footprints", "models"} or any(
                not isinstance(value, str) for value in values.values()
            ):
                raise KiCadError("Configuration KiCad : trois chemins texte attendus.")
            return LibraryRoots(**values)
        except (OSError, ValueError) as error:
            raise KiCadError(f"Configuration KiCad illisible : {error}") from error

    def _roots(self, roots: LibraryRoots) -> list[tuple[AssetType, Path]]:
        result = []
        for kind, value in zip(
            (AssetType.SYMBOL, AssetType.FOOTPRINT, AssetType.MODEL_3D),
            (roots.symbols, roots.footprints, roots.models),
            strict=True,
        ):
            if not value:
                continue
            path = Path(value).expanduser().resolve()
            if not path.is_dir():
                raise KiCadError(f"Dossier KiCad absent : {path}")
            for destination in (self.cache, self.config):
                if destination.resolve().is_relative_to(path):
                    raise KiCadError(
                        "Le cache et la configuration doivent être hors des bibliothèques."
                    )
            result.append((kind, path))
        return result

    def configure(self, roots: LibraryRoots) -> None:
        self._roots(roots)
        normalized = LibraryRoots(
            *(
                str(Path(value).expanduser().resolve()) if value else ""
                for value in (roots.symbols, roots.footprints, roots.models)
            )
        )
        content = "".join(
            f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in zip(
                ("symbols", "footprints", "models"),
                (normalized.symbols, normalized.footprints, normalized.models),
                strict=True,
            )
        )
        self._replace_text(self.config, content)

    @staticmethod
    def _replace_text(path: Path, content: str) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as error:
            raise KiCadError(f"Configuration non sauvegardée : {error}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _files(kind: AssetType, root: Path) -> Iterator[Path]:
        # os.walk explicitly reports directory read errors, unlike glob/rglob.
        def failed(error: OSError) -> None:
            raise error

        for directory, subdirs, names in os.walk(root, followlinks=False, onerror=failed):
            base = Path(directory)
            for name in sorted(subdirs):
                if (base / name).is_symlink():
                    raise KiCadError(f"Répertoire symbolique non indexé : {base / name}")
            subdirs.sort()
            if kind is AssetType.SYMBOL:
                subdirs[:] = []
            elif kind is AssetType.FOOTPRINT:
                if base == root:
                    subdirs[:] = [name for name in subdirs if name.endswith(".pretty")]
                else:
                    subdirs[:] = []
            for name in sorted(names):
                path = base / name
                extension = path.suffix.lower()
                if kind is AssetType.SYMBOL and extension in {".kicad_sym", ".lib"}:
                    yield path
                elif kind is AssetType.FOOTPRINT and extension in {".kicad_mod", ".mod"}:
                    yield path
                elif kind is AssetType.MODEL_3D and extension in {".step", ".stp", ".wrl"}:
                    yield path

    @staticmethod
    def _read(path: Path, text: bool) -> tuple[str, str]:
        if path.is_symlink():
            raise KiCadError("Fichier symbolique non indexé.")
        before = path.stat()
        if before.st_size == 0:
            raise KiCadError("Fichier vide.")
        if text and before.st_size > 64 * 1024 * 1024:
            raise KiCadError("Fichier S-expression supérieur à 64 Mio.")
        digest = hashlib.sha256()
        blocks: list[bytes] = []
        size = 0
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                size += len(block)
                if text and size > 64 * 1024 * 1024:
                    raise KiCadError("Fichier S-expression supérieur à 64 Mio.")
                digest.update(block)
                if text:
                    blocks.append(block)
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise KiCadError("Fichier modifié pendant l'indexation.")
        return digest.hexdigest(), b"".join(blocks).decode("utf-8") if text else ""

    def _references(self, kind: AssetType, root: Path, path: Path) -> list[KiCadReference]:
        relative = path.relative_to(root).as_posix()
        digest, text = self._read(path, kind is not AssetType.MODEL_3D)
        if kind is AssetType.MODEL_3D:
            library = path.parent.relative_to(root).as_posix()
            return [
                KiCadReference(
                    asset_type=kind,
                    library=library,
                    name=path.name,
                    relative_path=relative,
                    sha256=digest,
                    format_version=path.suffix.lower().lstrip("."),
                )
            ]
        if path.suffix.lower() not in {".kicad_sym", ".kicad_mod"}:
            raise KiCadError("Format KiCad historique non supporté.")
        tree = parse(text)
        version = check_version(tree, kind is AssetType.SYMBOL)
        if kind is AssetType.FOOTPRINT:
            if path.parent.suffix != ".pretty" or len(tree.atoms) != 2:
                raise KiCadError("Footprint attendu dans une bibliothèque .pretty.")
            if tree.atoms[1] != path.stem:
                raise KiCadError("Nom de footprint différent du nom de fichier.")
            return [
                KiCadReference(
                    asset_type=kind,
                    library=path.parent.stem,
                    name=path.stem,
                    relative_path=relative,
                    sha256=digest,
                    description=tree.value("descr"),
                    keywords=tree.value("tags"),
                    format_version=version,
                )
            ]
        result = []
        names: set[str] = set()
        for node in tree.children_named("symbol"):
            if len(node.atoms) != 2 or node.atoms[1] in names:
                raise KiCadError("Nom de symbole absent ou dupliqué.")
            names.add(node.atoms[1])
            description, keywords = symbol_metadata(node)
            result.append(
                KiCadReference(
                    asset_type=kind,
                    library=path.stem,
                    name=node.atoms[1],
                    relative_path=relative,
                    sha256=digest,
                    description=description,
                    keywords=keywords,
                    format_version=version,
                    extends=node.value("extends"),
                )
            )
        return result

    def rebuild(self, roots: LibraryRoots) -> IndexReport:
        sources = self._roots(roots)
        if not sources:
            raise KiCadError(
                "Aucune installation KiCad configurée ; découvrir ou saisir les dossiers."
            )
        temporary: Path | None = None
        issues: list[IndexIssue] = []
        count = 0
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache.parent, delete=False) as stream:
                temporary = Path(stream.name)
            with closing(sqlite3.connect(temporary)) as database, database:
                database.execute(f"PRAGMA user_version={SCHEMA}")
                columns = ", ".join(f"{name} TEXT NOT NULL" for name in FIELDS)
                database.execute(
                    f"CREATE TABLE entries (key TEXT PRIMARY KEY, {columns}, search TEXT)"
                )
                database.execute("CREATE TABLE issues (source TEXT, message TEXT)")
                database.execute("CREATE TABLE roots (symbols TEXT, footprints TEXT, models TEXT)")
                database.execute(
                    "INSERT INTO roots VALUES (?, ?, ?)",
                    (roots.symbols, roots.footprints, roots.models),
                )
                for kind, root in sources:
                    for path in self._files(kind, root):
                        try:
                            references = self._references(kind, root, path)
                            rows = [
                                (
                                    ref.key,
                                    *(str(getattr(ref, field)) for field in FIELDS),
                                    " ".join(
                                        (ref.identifier, ref.description, ref.keywords)
                                    ).casefold(),
                                )
                                for ref in references
                            ]
                            database.executemany(
                                "INSERT INTO entries VALUES ("
                                + ",".join("?" for _ in range(11))
                                + ")",
                                rows,
                            )
                            count += len(rows)
                        except (OSError, UnicodeError, KiCadError) as error:
                            issues.append(
                                IndexIssue(
                                    f"{kind.value}/{path.relative_to(root).as_posix()}", str(error)
                                )
                            )
                database.executemany(
                    "INSERT INTO issues VALUES (?, ?)",
                    [(issue.source, issue.message) for issue in issues],
                )
            # File failures yield a visible partial index.
            # Traversal/DB failures preserve the old cache.
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, self.cache)
            return IndexReport(count, tuple(issues))
        except (OSError, sqlite3.Error) as error:
            raise KiCadError(f"Index non reconstruit ; ancien cache conservé : {error}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _connection(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.cache.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if database.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
                raise KiCadError("Version du cache incompatible ; reconstruire l'index.")
        except (sqlite3.Error, KiCadError):
            database.close()
            raise
        return database

    def report(self) -> IndexReport:
        if not self.cache.exists():
            return IndexReport(0, (IndexIssue("index", "Index absent ; reconstruire l'index."),))
        try:
            with closing(self._connection()) as database:
                count = database.execute("SELECT count(*) FROM entries").fetchone()[0]
                issues = [IndexIssue(*row) for row in database.execute("SELECT * FROM issues")]
                row = database.execute("SELECT * FROM roots").fetchone()
                if row is None or len(row) != 3 or any(not isinstance(value, str) for value in row):
                    raise KiCadError("Métadonnées du cache invalides ; reconstruire l'index.")
                saved = LibraryRoots(*row)
                if saved != self.configuration():
                    issues.append(
                        IndexIssue("configuration", "Configuration modifiée ; reconstruire.")
                    )
                return IndexReport(count, tuple(issues))
        except sqlite3.Error as error:
            raise KiCadError(f"Cache illisible ; reconstruire l'index : {error}") from error

    def search(
        self, text: str, kind: AssetType | None = None, limit: int = 200
    ) -> list[KiCadReference]:
        if not self.cache.exists():
            return []
        try:
            with closing(self._connection()) as database:
                database.row_factory = sqlite3.Row
                rows = database.execute(
                    "SELECT * FROM entries WHERE instr(search, ?) > 0 "
                    "AND (? IS NULL OR asset_type = ?) ORDER BY key LIMIT ?",
                    (text.casefold(), kind, kind, limit),
                )
                return [
                    KiCadReference(
                        asset_type=AssetType(row["asset_type"]),
                        library=row["library"],
                        name=row["name"],
                        relative_path=row["relative_path"],
                        sha256=row["sha256"],
                        description=row["description"],
                        keywords=row["keywords"],
                        format_version=row["format_version"],
                        extends=row["extends"],
                    )
                    for row in rows
                ]
        except (sqlite3.Error, ValueError) as error:
            raise KiCadError(f"Cache illisible ; reconstruire l'index : {error}") from error

    def reference(self, key: str) -> KiCadReference | None:
        if not self.cache.exists():
            return None
        try:
            with closing(self._connection()) as database:
                row = database.execute(
                    "SELECT " + ", ".join(FIELDS) + " FROM entries WHERE key = ?", (key,)
                ).fetchone()
                if row is None:
                    return None
                return KiCadReference(
                    asset_type=AssetType(row[0]), **dict(zip(FIELDS[1:], row[1:], strict=True))
                )
        except (sqlite3.Error, ValueError) as error:
            raise KiCadError(f"Cache illisible ; reconstruire l'index : {error}") from error

    def verify_reference(self, reference: KiCadReference) -> None:
        roots = self.configuration()
        value = {
            AssetType.SYMBOL: roots.symbols,
            AssetType.FOOTPRINT: roots.footprints,
            AssetType.MODEL_3D: roots.models,
        }[reference.asset_type]
        if not value:
            raise KiCadError("Racine KiCad non configurée ; choix externe conservé.")
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            raise KiCadError("Racine KiCad absente ; choix externe conservé.")
        path = root / reference.relative_path
        if not path.resolve().is_relative_to(root):
            raise KiCadError("Référence sortant de la racine KiCad.")
        try:
            digest, _ = self._read(path, False)
        except OSError as error:
            raise KiCadError(f"Référence KiCad indisponible : {error}") from error
        if digest != reference.sha256:
            raise KiCadError("Fichier officiel modifié ; reconstruire l'index puis rechercher.")
