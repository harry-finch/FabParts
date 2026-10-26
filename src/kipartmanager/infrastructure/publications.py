"""Append-only manifests and retained source copies; COMMIT is installed last."""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.build import BuildPlan, BuildResource, BuildResult
from kipartmanager.domain.entities import DomainError
from kipartmanager.domain.publication import (
    BUILDER_VERSION,
    MANIFEST_VERSION,
    Publication,
    PublicationSnapshot,
    validate_version,
)
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.infrastructure.publication_manifest import canonical, decode_plan, manifest_base


def digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def safe_file(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if (
        not relative
        or any(p in {"", ".", ".."} for p in parts)
        or any(c in relative for c in "\\:\x00")
        or PurePosixPath(relative).is_absolute()
    ):
        raise DomainError("Chemin de publication non portable.")
    path = root.joinpath(*parts)
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise DomainError("Lien symbolique interdit dans une publication.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise DomainError("Chemin hors publication.")
    return path


class FrozenBuilder(LocalLibraryBuilder):
    """Reuse the deterministic M6 writer exclusively against retained dependencies."""

    def __init__(
        self, builder: LocalLibraryBuilder, sources: dict[str, tuple[Path, str, str, str]]
    ) -> None:
        super().__init__(builder.store, builder.index, builder.data_root)
        self.sources = sources

    def _source(self, resource: BuildResource) -> tuple[Path, str, str, str]:
        try:
            captured = self.sources[resource.choice.key]
        except KeyError as error:
            raise DomainError("Dépendance absente de l'instantané.") from error
        if resource.file:
            expected = resource.file.sha256
        else:
            assert resource.choice.reference is not None
            expected = resource.choice.reference.sha256
        if captured[1] != expected:
            raise DomainError("Hash de dépendance incompatible avec le choix figé.")
        return captured


class LocalPublications:
    def __init__(self, root: Path, builder: LocalLibraryBuilder) -> None:
        self.root, self.builder = root.resolve(), builder

    def _folder(self, collection_id: UUID, version: int) -> Path:
        # Validate identity before using it in filesystem paths.
        validate_version(version)
        return safe_file(self.root, f"{collection_id}/v{version:06d}")

    @staticmethod
    def _inventory(folder: Path) -> list[dict[str, Any]]:
        return [
            {"path": p.relative_to(folder).as_posix(), "sha256": digest, "size": size}
            for p in sorted(folder.rglob("*"))
            if p.is_file()
            for digest, size in (digest_file(p),)
        ]

    @staticmethod
    def _check_inventory(root: Path, entries: list[dict[str, Any]], prefix: str) -> None:
        expected = set()
        for entry in entries:
            path = safe_file(root, entry["path"])
            if not entry["path"].startswith(prefix + "/") or entry["path"] in expected:
                raise DomainError("Inventaire de publication invalide.")
            expected.add(entry["path"])
            if not path.is_file() or digest_file(path) != (entry["sha256"], entry["size"]):
                raise DomainError("Intégrité de publication incorrecte : " + entry["path"])
        folder = safe_file(root, prefix)
        actual = {
            p.relative_to(root).as_posix()
            for p in folder.rglob("*")
            if p.is_file() or p.is_symlink()
        }
        if actual != expected:
            raise DomainError("Fichier supplémentaire ou manquant dans la publication.")

    @staticmethod
    def _install(
        staging: Path, target: Path, confirm: Callable[[], None], *, committed: bool
    ) -> None:
        installed: list[tuple[Path, int]] = []
        directories: set[Path] = set()
        reserved = complete = False
        try:
            target.mkdir()
            reserved = True
            if not committed:
                marker = target / "BUILDING"
                marker.write_text("Reconstruction incomplète\n")
                installed.append((marker, marker.stat().st_ino))
            for source in sorted(staging.rglob("*")):
                if not source.is_file() or source.name == "COMMIT":
                    continue
                relative = source.relative_to(staging)
                destination = target / relative
                for parent in reversed(destination.parents):
                    if parent != target and parent.is_relative_to(target):
                        if not parent.exists():
                            parent.mkdir()
                            directories.add(parent)
                os.link(source, destination)
                installed.append((destination, destination.stat().st_ino))
            confirm()
            for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                LocalAssetStore._sync_directory(directory)
            if committed:
                os.link(staging / "COMMIT", target / "COMMIT")
                installed.append((target / "COMMIT", (target / "COMMIT").stat().st_ino))
            else:
                (target / "BUILDING").unlink()
            LocalAssetStore._sync_directory(target)
            LocalAssetStore._sync_directory(target.parent)
            complete = True
        finally:
            if reserved and not complete:
                for path, inode in reversed(installed):
                    if not path.is_symlink() and path.exists() and path.stat().st_ino == inode:
                        path.unlink()
                for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
                try:
                    target.rmdir()
                except OSError:
                    pass

    def publish(
        self, snapshot: PublicationSnapshot, version: int, confirm: Callable[[], None]
    ) -> Publication:
        target = self._folder(snapshot.plan.collection_id, version)
        if target.exists():
            raise DomainError("Version déjà existante ; publication immuable.")
        roots = self.builder.index.configuration()
        if any(
            self.root.is_relative_to(Path(path).resolve())
            for path in (roots.symbols, roots.footprints, roots.models)
            if path
        ):
            raise DomainError("Stockage des publications dans une bibliothèque source interdit.")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            for directory in (target.parent, self.root, self.root.parent):
                LocalAssetStore._sync_directory(directory)
            with tempfile.TemporaryDirectory(prefix=".pending-", dir=target.parent) as temporary:
                staging = Path(temporary)
                sources = {}
                dependencies = []
                for part in snapshot.plan.parts:
                    for resource in part.resources:
                        if resource.choice.key in sources:
                            continue
                        source, digest, extension, name = self.builder._source(resource)
                        relative = f"inputs/{digest}{extension}"
                        retained = staging / relative
                        if not retained.exists():
                            retained.parent.mkdir(parents=True, exist_ok=True)
                            actual, size = self.builder.store._copy(source, retained)
                            if actual != digest:
                                raise DomainError("Source modifiée pendant la publication.")
                        else:
                            actual, size = digest_file(retained)
                        self.builder._source(resource)
                        sources[resource.choice.key] = (retained, digest, extension, name)
                        dependencies.append(
                            {
                                "key": resource.choice.key,
                                "path": relative,
                                "sha256": digest,
                                "size": size,
                                "extension": extension,
                                "original_name": name,
                                "symbol_name": resource.file.symbol_name if resource.file else "",
                                "origin": resource.origin,
                            }
                        )
                artifacts = staging / "artifacts"
                artifacts.mkdir()
                FrozenBuilder(self.builder, sources)._construct(snapshot.plan, artifacts)
                confirm()
                data = manifest_base(snapshot, version, datetime.now(UTC).isoformat())
                data["dependencies"] = dependencies
                data["inputs"] = [
                    {**entry, "path": "inputs/" + entry["path"]}
                    for entry in self._inventory(staging / "inputs")
                ]
                data["artifacts"] = [
                    {**entry, "path": "artifacts/" + entry["path"]}
                    for entry in self._inventory(artifacts)
                ]
                encoded = canonical(data)
                digest = hashlib.sha256(encoded).hexdigest()
                self.builder._write(staging / "manifest.json", encoded.decode())
                self.builder._write(staging / "COMMIT", digest + "\n")
                publication = self._summary(data, digest)
                self._check_inventory(staging, data["inputs"], "inputs")
                self._check_inventory(staging, data["artifacts"], "artifacts")

                def final_check() -> None:
                    confirm()
                    self._check_inventory(target, data["inputs"], "inputs")
                    self._check_inventory(target, data["artifacts"], "artifacts")
                    if (target / "manifest.json").read_bytes() != encoded:
                        raise DomainError("Manifest modifié avant engagement.")

                self._install(staging, target, final_check, committed=True)
                return publication
        except OSError as error:
            raise DomainError("Publication non engagée : " + str(error)) from error

    @staticmethod
    def _summary(data: dict[str, Any], digest: str) -> Publication:
        plan = decode_plan(data["plan"])
        if (
            type(data["schema"]) is not int
            or data["schema"] != MANIFEST_VERSION
            or data["builder"] != BUILDER_VERSION
        ):
            raise DomainError("Version de manifest ou builder non prise en charge.")
        validation = data["validation"]
        if (
            validation["subject_key"] != f"Collection:{plan.collection_id.hex}"
            or validation["fingerprint"] != plan.fingerprint
            or type(validation["warnings_accepted"]) is not bool
            or validation["level"] not in {"PASS", "WARNING"}
            or (validation["level"] == "WARNING" and not validation["warnings_accepted"])
            or not plan.parts
            or len({p.identity for p in plan.parts}) != len(plan.parts)
        ):
            raise DomainError("Qualification ou composition de publication invalide.")
        return Publication(
            plan.collection_id,
            plan.collection_name,
            data["version"],
            data["created_at"],
            plan.fingerprint,
            digest,
        )

    def _load(self, publication: Publication) -> tuple[Path, dict[str, Any], BuildPlan]:
        root = self._folder(publication.collection_id, publication.version)
        try:
            commit = safe_file(root, "COMMIT").read_text().strip()
            path = safe_file(root, "manifest.json")
            if path.stat().st_size > 64 * 1024 * 1024:
                raise DomainError("Manifest trop volumineux.")
            encoded = path.read_bytes()
            digest = hashlib.sha256(encoded).hexdigest()
            if commit != digest or digest != publication.manifest_sha256:
                raise DomainError("Manifest de publication modifié ou non engagé.")
            data = json.loads(encoded)
            if self._summary(data, digest) != publication:
                raise DomainError("Identité du manifest incohérente.")
            return root, data, decode_plan(data["plan"])
        except DomainError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise DomainError("Publication illisible ou incomplète.") from error

    def list_publications(self, collection_id: UUID | None = None) -> tuple[Publication, ...]:
        if not self.root.exists():
            return ()
        if not self.root.is_dir():
            raise DomainError("Stockage des publications inaccessible.")
        result = []
        for folder in sorted(self.root.glob("*/v*")):
            if collection_id is not None and folder.parent.name != str(collection_id):
                continue
            if not (folder / "COMMIT").exists():
                continue
            try:
                manifest = safe_file(folder, "manifest.json")
                if manifest.stat().st_size > 64 * 1024 * 1024:
                    raise DomainError("Manifest trop volumineux.")
                encoded = manifest.read_bytes()
                publication = self._summary(
                    json.loads(encoded), hashlib.sha256(encoded).hexdigest()
                )
                if self._folder(publication.collection_id, publication.version) != folder:
                    raise DomainError("Publication rangée sous une identité incorrecte.")
                self._load(publication)
                result.append(publication)
            except DomainError:
                raise
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                raise DomainError(
                    "Historique illisible ; aucune version partielle acceptée."
                ) from error
        return tuple(result)

    def occupied_versions(self, collection_id: UUID) -> tuple[int, ...]:
        # Include incomplete reservations; a missing COMMIT never frees a number.
        parent = safe_file(self.root, str(collection_id))
        return tuple(
            sorted(
                int(p.name[1:])
                for p in parent.glob("v[0-9][0-9][0-9][0-9][0-9][0-9]")
                if 1 <= int(p.name[1:]) <= 999999
            )
        )

    def details(self, publication: Publication) -> tuple[BuildPlan, str, bool, tuple[str, ...]]:
        _, data, plan = self._load(publication)
        return (
            plan,
            data["validation"]["level"],
            data["validation"]["warnings_accepted"],
            tuple(e["path"] for e in data["artifacts"]),
        )

    def _sources(
        self, root: Path, data: dict[str, Any], plan: BuildPlan
    ) -> dict[str, tuple[Path, str, str, str]]:
        self._check_inventory(root, data["inputs"], "inputs")
        required = {r.choice.key: r for part in plan.parts for r in part.resources}
        inventory = {e["path"]: (e["sha256"], e["size"]) for e in data["inputs"]}
        sources = {}
        for dep in data["dependencies"]:
            resource = required[dep["key"]]
            descriptor = AssetFile(
                dep["sha256"],
                dep["size"],
                dep["extension"],
                dep["original_name"],
                dep.get("symbol_name", ""),
            )
            if (
                dep["key"] in sources
                or dep["path"] != f"inputs/{descriptor.sha256}{descriptor.extension}"
                or inventory.get(dep["path"]) != (descriptor.sha256, descriptor.size_bytes)
                or descriptor.asset_type != resource.asset_type
                or dep["origin"] != resource.origin
                or (resource.file is not None and resource.file != descriptor)
            ):
                raise DomainError("Dépendance incompatible avec les associations figées.")
            if resource.choice.reference:
                ref = resource.choice.reference
                if (
                    ref.sha256 != descriptor.sha256
                    or PurePosixPath(ref.relative_path).name != descriptor.original_name
                ):
                    raise DomainError("Référence officielle incohérente dans le manifest.")
            sources[dep["key"]] = (
                safe_file(root, dep["path"]),
                descriptor.sha256,
                descriptor.extension,
                descriptor.original_name,
            )
        if set(sources) != set(required):
            raise DomainError("Dépendance manquante dans l'instantané.")
        if {d[0].relative_to(root).as_posix() for d in sources.values()} != set(inventory):
            raise DomainError("Dépendance non référencée dans l'instantané.")
        return sources

    def verify(self, publication: Publication) -> None:
        try:
            root, data, plan = self._load(publication)
            self._sources(root, data, plan)
            self._check_inventory(root, data["artifacts"], "artifacts")
        except DomainError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise DomainError("Publication non vérifiable.") from error

    def rebuild(self, publication: Publication, destination: str) -> BuildResult:
        target = Path(destination).absolute()
        protected = [self.root, self.builder.data_root, self.builder.store.root]
        roots = self.builder.index.configuration()
        protected.extend(
            Path(p).resolve() for p in (roots.symbols, roots.footprints, roots.models) if p
        )
        if any(target.resolve().is_relative_to(p) for p in protected):
            raise DomainError("Choisir une destination hors données et bibliothèques sources.")
        if target.exists() or target.is_symlink():
            raise DomainError("Destination déjà existante ; aucun remplacement autorisé.")
        try:
            root, data, plan = self._load(publication)
            sources = self._sources(root, data, plan)
            with tempfile.TemporaryDirectory(
                prefix=".kipart-rebuild-", dir=target.parent
            ) as temporary:
                staging = Path(temporary)
                count, packages = FrozenBuilder(self.builder, sources)._construct(plan, staging)
                expected = [
                    {**e, "path": e["path"].removeprefix("artifacts/")} for e in data["artifacts"]
                ]
                if self._inventory(staging) != expected:
                    raise DomainError("Reconstruction différente de la version publiée.")

                def confirm() -> None:
                    self._load(publication)
                    self._check_inventory(root, data["inputs"], "inputs")
                    if self._inventory(target) != expected:
                        # BUILDING is deliberately not part of the output inventory.
                        actual = [e for e in self._inventory(target) if e["path"] != "BUILDING"]
                        if actual != expected:
                            raise DomainError("Sorties modifiées pendant la reconstruction.")

                self._install(staging, target, confirm, committed=False)
                return BuildResult(
                    str(target), plan.library, count, packages, tuple(e["path"] for e in expected)
                )
        except DomainError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise DomainError("Reconstruction non terminée.") from error
