"""Standalone copy-mode library builder; no catalogue/store writes or versions."""

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from kipartmanager.domain.build import BuildPlan, BuildResource, BuildResult
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_parser import Node, parse
from kipartmanager.infrastructure.kicad_writer import (
    footprint,
    library,
    serialize,
    string,
    symbols,
)
from kipartmanager.infrastructure.resource_probe import footprint_info, symbol_info


class LocalLibraryBuilder:
    def __init__(self, store: LocalAssetStore, index: LocalKiCadIndex, data_root: Path) -> None:
        self.store, self.index, self.data_root = store, index, data_root.resolve()

    def _source(self, resource: BuildResource) -> tuple[Path, str, str, str]:
        if resource.file:
            self.store.verify(resource.file)
            return (
                self.store._path(resource.file),
                resource.file.sha256,
                resource.file.extension,
                resource.file.original_name,
            )
        reference = resource.choice.reference
        assert reference is not None
        self.index.verify_reference(reference)
        roots = self.index.configuration()
        folder = {
            AssetType.SYMBOL: roots.symbols,
            AssetType.FOOTPRINT: roots.footprints,
            AssetType.MODEL_3D: roots.models,
        }[reference.asset_type]
        path = Path(folder) / reference.relative_path
        return path, reference.sha256, path.suffix.lower(), path.name

    def _copy(self, resource: BuildResource, destination: Path) -> tuple[str, str]:
        path, digest, extension, name = self._source(resource)
        destination.parent.mkdir(parents=True, exist_ok=True)
        actual, _ = self.store._copy(path, destination)
        if actual != digest:
            raise DomainError("Ressource modifiée pendant la construction ; revalider.")
        if resource.asset_type is AssetType.MODEL_3D:
            self._check_model_dependencies(destination, extension)
        self._source(resource)
        return extension, name

    @staticmethod
    def _check_model_dependencies(path: Path, extension: str) -> None:
        pattern = (
            rb"\burl\b"
            if extension == ".wrl"
            else rb"\b(?:EXTERNALLY_DEFINED|EXTERNAL_SOURCE|EXTERNAL_FILE)[A-Z_]*\b"
        )
        tail = b""
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                data = tail + chunk
                if re.search(pattern, data):
                    raise DomainError("Dépendance externe de modèle 3D non prise en charge en M6.")
                tail = data[-128:]

    def _tree(self, resource: BuildResource, staging: Path) -> Node:
        captured = staging / ".inputs" / hashlib.sha256(resource.choice.key.encode()).hexdigest()
        self._copy(resource, captured)
        if captured.stat().st_size > 64 * 1024 * 1024:
            raise DomainError("S-expression supérieure à 64 Mio.")
        return parse(captured.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def _construct(self, plan: BuildPlan, staging: Path) -> tuple[int, int]:
        nickname = plan.library
        trees: list[Node] = []
        entries: list[Node] = []
        packages: dict[UUID, tuple[BuildResource, BuildResource | None]] = {}
        for part in plan.parts:
            resources = {r.asset_type: r for r in part.resources}
            symbol = resources[AssetType.SYMBOL]
            fp = resources[AssetType.FOOTPRINT]
            model = resources.get(AssetType.MODEL_3D)
            datasheet = resources.get(AssetType.DATASHEET)
            mechanical = (fp, model)
            if part.package_id in packages and packages[part.package_id] != mechanical:
                raise DomainError("Choix de Package modifiés pendant la préparation.")
            if part.package_id not in packages:
                packages[part.package_id] = mechanical
                model_name = model_uri = ""
                if model:
                    _, digest, extension, model_name = self._source(model)
                    relative = f"{nickname}.3dshapes/{digest}{extension}"
                    target = staging / relative
                    if not target.exists():
                        self._copy(model, target)
                    model_uri = "${KIPRJMOD}/" + relative
                node = footprint(
                    self._tree(fp, staging), part.footprint_name, model_name, model_uri
                )
                self._write(
                    staging / f"{nickname}.pretty/{part.footprint_name}.kicad_mod",
                    serialize(node) + "\n",
                )
            datasheet_uri = ""
            if datasheet:
                _, digest, extension, _ = self._source(datasheet)
                relative = f"datasheets/{digest}{extension}"
                target = staging / relative
                if not target.exists():
                    self._copy(datasheet, target)
                datasheet_uri = "${KIPRJMOD}/" + relative
            tree = self._tree(symbol, staging)
            trees.append(tree)
            reference = symbol.choice.reference
            entries.extend(
                symbols(
                    tree,
                    reference.name if reference else symbol.file.symbol_name if symbol.file else "",
                    part.symbol_name,
                    f"{nickname}:{part.footprint_name}",
                    part.name,
                    datasheet_uri,
                )
            )
        root = library(trees, entries)
        self._write(staging / f"{nickname}.kicad_sym", serialize(root) + "\n")
        for table, suffix in (("sym-lib-table", ".kicad_sym"), ("fp-lib-table", ".pretty")):
            tag = "sym_lib_table" if table == "sym-lib-table" else "fp_lib_table"
            self._write(
                staging / table,
                f'({tag} (lib (name {string(nickname)}) (type "KiCad") '
                f'(uri "${{KIPRJMOD}}/{nickname}{suffix}") (options "") (descr "")))\n',
            )
        self._write(
            staging / "UTILISATION.txt",
            "KiPart Manager M6 — copie autonome de la collection courante\n"
            f"Collection : {plan.collection_id}\nBibliothèque : {nickname}\n"
            "Placer ces fichiers au niveau du dossier projet KiCad : "
            "${KIPRJMOD} désigne ce dossier.\n"
            "Les tables fournies sont des tables de projet ; ne pas écraser une table existante.\n"
            "Ajouter leurs entrées aux tables du projet si nécessaire.\n"
            "Symboles et footprints conservent leurs versions de format source ; "
            "utiliser un KiCad assez récent.\n"
            "Contrôles M5 partiels : géométrie 3D et contenu PDF non certifiés.\n"
            "Ce dossier est un artefact reconstruisible M6, sans version publiée ni manifest M7.\n"
            + "\n".join(f"{p.symbol_name}\t{p.name}\t{p.footprint_name}" for p in plan.parts)
            + "\n",
        )
        self._write(
            staging / "SOURCES.txt",
            "Traçabilité des ressources choisies ; pas un manifest de publication versionnée.\n"
            "Part UUID\tRôle\tIdentité source\tOrigine\tSHA-256 source\n"
            + "\n".join(
                f"{part.identity}\t{r.asset_type.value}\t{r.choice.key}\t{r.origin}\t"
                + (
                    r.file.sha256
                    if r.file
                    else r.choice.reference.sha256
                    if r.choice.reference
                    else ""
                )
                for part in plan.parts
                for r in part.resources
            )
            + "\n",
        )
        self._validate_outputs(plan, staging)
        shutil.rmtree(staging / ".inputs")
        return len(plan.parts), len(packages)

    @staticmethod
    def _validate_outputs(plan: BuildPlan, staging: Path) -> None:
        root = parse((staging / f"{plan.library}.kicad_sym").read_text())
        for part in plan.parts:
            symbol_info(root, part.symbol_name)
            fp = parse(
                (staging / f"{plan.library}.pretty/{part.footprint_name}.kicad_mod").read_text()
            )
            footprint_info(fp)
            for model in fp.children_named("model"):
                uri = model.atoms[1]
                if (
                    not uri.startswith("${KIPRJMOD}/")
                    or not (staging / uri.removeprefix("${KIPRJMOD}/")).is_file()
                ):
                    raise DomainError("Lien 3D produit non résolu.")
        # Reject known leftover external file properties, not arbitrary descriptive text.
        for node in root.children_named("symbol"):
            for prop in node.children_named("property"):
                if len(prop.atoms) >= 3 and prop.atoms[1] in {"Footprint", "Datasheet"}:
                    value = prop.atoms[2]
                    if prop.atoms[1] == "Footprint":
                        if value and not value.startswith(plan.library + ":"):
                            raise DomainError("Lien footprint produit externe.")
                    elif value and (
                        not value.startswith("${KIPRJMOD}/")
                        or not (staging / value.removeprefix("${KIPRJMOD}/")).is_file()
                    ):
                        raise DomainError("Lien datasheet produit non résolu.")

    def build(self, plan: BuildPlan, destination: str, confirm: Callable[[], None]) -> BuildResult:
        target = Path(destination).absolute()
        roots = self.index.configuration()
        protected = [self.data_root, self.store.root]
        protected.extend(
            Path(p).resolve() for p in (roots.symbols, roots.footprints, roots.models) if p
        )
        if any(target.resolve().is_relative_to(p) for p in protected):
            raise DomainError(
                "Choisir un dossier de sortie hors des données et bibliothèques sources."
            )
        if target.exists() or target.is_symlink():
            raise DomainError("Destination déjà existante ; aucun remplacement autorisé.")
        published: list[Path] = []
        directories: set[Path] = set()
        reserved = False
        completed = False
        try:
            with tempfile.TemporaryDirectory(
                prefix=".kipart-build-", dir=target.parent
            ) as temporary:
                staging = Path(temporary)
                count, package_count = self._construct(plan, staging)
                confirm()
                files = tuple(
                    sorted(
                        p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()
                    )
                )
                target.mkdir()  # Exclusive reservation; never adopt an existing folder.
                reserved = True
                marker = target / "BUILDING"
                published.append(marker)
                self._write(marker, "Construction M6 incomplète tant que ce fichier existe.\n")
                for relative in files:
                    output = target / relative
                    if output.parent != target:
                        output.parent.mkdir(exist_ok=True)
                        directories.add(output.parent)
                    os.link(staging / relative, output)  # Exclusive, no overwritten file.
                    published.append(output)
                confirm()
                marker.unlink()
                self.store._sync_directory(target)
                completed = True
                return BuildResult(str(target), plan.library, count, package_count, files)
        except (OSError, UnicodeError) as error:
            raise DomainError(f"Construction impossible : {error}.") from error
        finally:
            if reserved and not completed:
                # Only our own links are removed; preserve unexpected external additions.
                for path in reversed(published):
                    path.unlink(missing_ok=True)
                for folder in sorted(directories, reverse=True):
                    try:
                        folder.rmdir()
                    except OSError:
                        pass
                try:
                    target.rmdir()
                except OSError:
                    pass
