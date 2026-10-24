"""Bounded ZIP transport and serialized, non-replacing catalogue import."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.bundles import BundlePreview
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    DomainError,
    Entity,
    Package,
    Part,
)
from kipartmanager.domain.publication import Publication
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.catalogue import ROWS, SqliteCatalogue
from kipartmanager.infrastructure.models import ChoiceRow, CollectionRow
from kipartmanager.infrastructure.publication_manifest import canonical, decode_plan
from kipartmanager.infrastructure.publications import FrozenBuilder, LocalPublications, safe_file

MAX_BYTES = 1024 * 1024 * 1024
MAX_FILES = 10000
MAX_JSON = 64 * 1024 * 1024


def portable_provenance(source: str, original_name: str) -> str:
    if (
        source.startswith(("https://", "http://"))
        or (
            source.startswith(("kicad:", "kiparts:asset:", "local-file:"))
            and not any(c in source for c in "/\\")
        )
        or not any(c in source for c in "/\\:")
    ):
        return source
    return "local-file:" + original_name


def strict_json(encoded: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise DomainError("Clé JSON dupliquée.")
            result[key] = value
        return result

    if len(encoded) > MAX_JSON:
        raise DomainError("Manifest trop volumineux.")
    result = json.loads(encoded, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise DomainError("Manifest JSON invalide.")
    return result


class LocalBundles:
    def __init__(self, repository: SqliteCatalogue, publications: LocalPublications) -> None:
        self.repository, self.publications = repository, publications
        self.store = publications.builder.store

    def _protect(self, path: Path) -> None:
        roots = self.publications.builder.index.configuration()
        protected = [
            self.store.root,
            self.publications.root,
            self.publications.builder.data_root,
            *(Path(p).resolve() for p in (roots.symbols, roots.footprints, roots.models) if p),
        ]
        if any(path.resolve().is_relative_to(root) for root in protected):
            raise DomainError("Choisir une archive hors données et bibliothèques sources.")

    def export(self, publication: Publication, destination: str) -> None:
        target = Path(destination).absolute()
        self._protect(target)
        if target.suffix.lower() != ".kiparts":
            raise DomainError("L'archive doit porter l'extension .kiparts.")
        if target.exists() or target.is_symlink():
            raise DomainError("Destination existante ; aucun remplacement autorisé.")
        try:
            self.publications.verify(publication)
            root, data, _ = self.publications._load(publication)
            inventory = self.publications._inventory(root)
            labels = {}
            provenance = {}
            entities, _ = self._projection(data, {})
            for entity in entities:
                current = self.repository.get(type(entity), entity.id)
                if isinstance(current, Package):
                    labels[str(entity.id)] = current.name
                if (
                    isinstance(current, Asset)
                    and isinstance(entity, Asset)
                    and current.file == entity.file
                    and current.origin == entity.origin
                ):
                    labels[str(entity.id)] = current.name
                    assert current.file is not None
                    provenance[str(entity.id)] = portable_provenance(
                        current.source, current.file.original_name
                    )
            envelope = {
                "format": "kiparts",
                "schema": 1,
                "publication_sha256": publication.manifest_sha256,
                "labels": labels,
                "provenance": provenance,
                "files": inventory,
            }
            if len(inventory) > MAX_FILES or sum(e["size"] for e in inventory) > MAX_BYTES:
                raise DomainError("Publication supérieure aux limites du format .kiparts.")
            with tempfile.TemporaryDirectory(prefix=".kiparts-export-", dir=target.parent) as temp:
                staging = Path(temp) / "bundle.kiparts"
                with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", canonical(envelope))
                    for entry in inventory:
                        source = safe_file(root, entry["path"])
                        archive.write(source, "publication/" + entry["path"])
                # Reread the completed archive before installing it exclusively.
                with self._archive(str(staging)):
                    pass
                self.publications.verify(publication)
                os.link(staging, target)
                self.store._sync_directory(target.parent)
        except DomainError:
            raise
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
            raise DomainError("Export .kiparts non terminé.") from error

    @contextmanager
    def _archive(
        self, source: str
    ) -> Iterator[tuple[Path, dict[str, Any], dict[str, Any], Publication]]:
        try:
            with tempfile.TemporaryDirectory(prefix="kiparts-read-") as temp:
                staging = Path(temp).resolve()
                with zipfile.ZipFile(source) as archive:
                    entries = archive.infolist()
                    if (
                        len(entries) > MAX_FILES + 1
                        or sum(e.file_size for e in entries) > MAX_BYTES
                    ):
                        raise DomainError("Archive trop volumineuse.")
                    names = set()
                    for entry in entries:
                        if entry.orig_filename != entry.filename:
                            raise DomainError("Nom ZIP contenant un caractère nul.")
                        safe_file(staging, entry.filename)
                        mode = entry.external_attr >> 16
                        if (
                            entry.filename in names
                            or entry.is_dir()
                            or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                            or entry.flag_bits & 1
                            or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                        ):
                            raise DomainError("Entrée ZIP dupliquée, lien ou format interdit.")
                        names.add(entry.filename)
                    if archive.getinfo("manifest.json").file_size > MAX_JSON:
                        raise DomainError("Manifest trop volumineux.")
                    envelope = strict_json(archive.read("manifest.json"))
                    if (
                        envelope["format"] != "kiparts"
                        or type(envelope["schema"]) is not int
                        or envelope["schema"] != 1
                    ):
                        raise DomainError("Format .kiparts non pris en charge.")
                    expected = {"manifest.json"}
                    for entry in envelope["files"]:
                        name = "publication/" + entry["path"]
                        safe_file(staging, name)
                        if name in expected:
                            raise DomainError("Inventaire dupliqué.")
                        expected.add(name)
                        if name not in names:
                            raise DomainError("Fichier absent de l'archive.")
                        info = archive.getinfo(name)
                        if type(entry["size"]) is not int or info.file_size != entry["size"]:
                            raise DomainError("Taille d'archive incohérente.")
                        destination = safe_file(staging, name)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        digest = hashlib.sha256()
                        size = 0
                        with archive.open(info) as reader, destination.open("xb") as writer:
                            while chunk := reader.read(1024 * 1024):
                                size += len(chunk)
                                if size > entry["size"]:
                                    raise DomainError(
                                        "Décompression supérieure à la taille déclarée."
                                    )
                                digest.update(chunk)
                                writer.write(chunk)
                        if digest.hexdigest() != entry["sha256"] or size != entry["size"]:
                            raise DomainError("Hash de l'archive incorrect : " + entry["path"])
                    if names != expected:
                        raise DomainError("Fichier supplémentaire dans l'archive.")
                root = staging / "publication"
                encoded = safe_file(root, "manifest.json").read_bytes()
                data = strict_json(encoded)
                manifest_digest = hashlib.sha256(encoded).hexdigest()
                if (
                    manifest_digest != envelope["publication_sha256"]
                    or safe_file(root, "COMMIT").read_text().strip() != manifest_digest
                ):
                    raise DomainError("Manifest historique altéré.")
                publication = self.publications._summary(data, manifest_digest)
                plan = decode_plan(data["plan"])
                sources = self.publications._sources(root, data, plan)
                self.publications._check_inventory(root, data["artifacts"], "artifacts")
                permitted = {
                    "manifest.json",
                    "COMMIT",
                    *(e["path"] for e in data["inputs"]),
                    *(e["path"] for e in data["artifacts"]),
                }
                if {e["path"] for e in envelope["files"]} != permitted:
                    raise DomainError("Inventaire historique incompatible.")
                regenerated = staging / "regenerated"
                regenerated.mkdir()
                FrozenBuilder(self.publications.builder, sources)._construct(plan, regenerated)
                expected_artifacts = [
                    {**e, "path": e["path"].removeprefix("artifacts/")} for e in data["artifacts"]
                ]
                if self.publications._inventory(regenerated) != expected_artifacts:
                    raise DomainError("Artefacts différents de la construction portable attendue.")
                self._projection(data, envelope["labels"], envelope.get("provenance", {}))
                yield root, data, envelope, publication
        except DomainError:
            raise
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            UnicodeError,
            zipfile.BadZipFile,
            RuntimeError,
        ) as error:
            raise DomainError("Archive .kiparts illisible ou incomplète.") from error

    @staticmethod
    def _projection(
        data: dict[str, Any], labels: dict[str, str], provenance: dict[str, str] | None = None
    ) -> tuple[list[Entity], dict[str, tuple[ResourceChoice, ...]]]:
        if provenance is None:
            provenance = {}
        if not isinstance(provenance, dict):
            raise DomainError("Provenance de catalogue invalide.")
        plan = decode_plan(data["plan"])
        assets: dict[UUID, Asset] = {}
        packages: dict[UUID, Package] = {}
        parts: list[Part] = []
        choices: dict[str, tuple[ResourceChoice, ...]] = {}
        dependencies = {d["key"]: d for d in data["dependencies"]}
        for built in plan.parts:
            per_part: list[ResourceChoice] = []
            per_package: list[ResourceChoice] = []
            for resource in built.resources:
                dep = dependencies[resource.choice.key]
                ref = resource.choice.reference
                if ref and resource.origin != ref.origin.value:
                    raise DomainError("Origine officielle incohérente.")
                identity = resource.choice.asset_id or uuid5(
                    NAMESPACE_URL, "kiparts:" + resource.choice.key + ":" + dep["sha256"]
                )
                file = resource.file or AssetFile(
                    dep["sha256"],
                    dep["size"],
                    dep["extension"],
                    dep["original_name"],
                    ref.name if ref and resource.asset_type is AssetType.SYMBOL else "",
                )
                asset = Asset(
                    id=identity,
                    name=labels.get(
                        str(identity), ref.name if ref else Path(file.original_name).stem
                    ),
                    asset_type=resource.asset_type,
                    origin=AssetOrigin(resource.origin),
                    source=ref.key
                    if ref
                    else provenance.get(str(identity), "kiparts:asset:" + str(identity)),
                    file=file,
                )
                if identity in assets and assets[identity] != asset:
                    raise DomainError("UUID d'asset associé à des contenus différents.")
                assets[identity] = asset
                choice = ResourceChoice(resource.asset_type, identity)
                (
                    per_package
                    if resource.asset_type in {AssetType.FOOTPRINT, AssetType.MODEL_3D}
                    else per_part
                ).append(choice)
            if not {AssetType.SYMBOL}.issubset({c.asset_type for c in per_part}) or {
                c.asset_type for c in per_package
            }.isdisjoint({AssetType.FOOTPRINT}):
                raise DomainError("Ressources PCB obligatoires absentes.")
            if len({c.asset_type for c in per_part + per_package}) != len(per_part + per_package):
                raise DomainError("Rôle dupliqué dans l'instantané.")
            package = Package(
                id=built.package_id,
                name=labels.get(str(built.package_id), "Package " + built.package_id.hex[:8]),
                asset_ids=tuple(c.asset_id for c in per_package if c.asset_id),
            )
            if package.id in packages and (
                packages[package.id] != package
                or choices["Package:" + package.id.hex]
                != tuple(sorted(per_package, key=lambda c: c.asset_type))
            ):
                raise DomainError("Package partagé incohérent.")
            packages[package.id] = package
            choices["Package:" + package.id.hex] = tuple(
                sorted(per_package, key=lambda c: c.asset_type)
            )
            part = Part(
                id=built.identity,
                name=built.name,
                package_id=package.id,
                asset_ids=tuple(c.asset_id for c in per_part if c.asset_id),
            )
            parts.append(part)
            choices["Part:" + part.id.hex] = tuple(sorted(per_part, key=lambda c: c.asset_type))
        entities: list[Entity] = [
            *assets.values(),
            *packages.values(),
            *parts,
            Collection(
                id=plan.collection_id,
                name=plan.collection_name,
                part_ids=tuple(p.id for p in parts),
            ),
        ]
        if (
            not isinstance(labels, dict)
            or any(not isinstance(v, str) or not v.strip() for v in labels.values())
            or set(labels) - {str(e.id) for e in entities if isinstance(e, (Asset, Package))}
        ):
            raise DomainError("Libellés de catalogue invalides.")
        if not isinstance(provenance, dict) or set(provenance) - {str(a) for a in assets}:
            raise DomainError("Provenance de catalogue invalide.")
        for provenance_id, source in provenance.items():
            provenance_file = assets[UUID(provenance_id)].file
            assert provenance_file is not None
            if not isinstance(source, str) or (
                source != portable_provenance(source, provenance_file.original_name)
                and source != "local-file:" + provenance_file.original_name
                and source != "kiparts:asset:" + provenance_id
            ):
                raise DomainError("Provenance non portable.")
        return entities, choices

    def _conflicts(
        self,
        session: Session,
        entities: list[Entity],
        choices: dict[str, tuple[ResourceChoice, ...]],
        publication: Publication,
    ) -> tuple[str, ...]:
        conflicts = []
        for entity in entities:
            row = session.get(ROWS[type(entity)], entity.id)
            if row:
                current = self.repository._entity(session, row)
                if isinstance(current, Asset) and isinstance(entity, Asset):
                    portable_source = (
                        portable_provenance(current.source, current.file.original_name)
                        if current.file
                        else current.source
                    )
                    compatible = replace(
                        current, source=entity.source, provenance=entity.provenance
                    ) == entity and (
                        portable_source == entity.source
                        or entity.source == "kiparts:asset:" + str(entity.id)
                    )
                elif isinstance(current, Part) and isinstance(entity, Part):
                    compatible = replace(current, description="", state=entity.state) == entity
                elif isinstance(current, Package) and isinstance(entity, Package):
                    compatible = replace(current, description="") == entity
                else:
                    compatible = current == entity
                if not compatible:
                    conflicts.append(
                        f"{type(entity).__name__} « {getattr(entity, 'name', '')} » : "
                        f"UUID {entity.id} différent."
                    )
            if isinstance(entity, Collection):
                other = session.scalar(
                    select(CollectionRow).where(
                        CollectionRow.name == entity.name, CollectionRow.id != entity.id
                    )
                )
                if other:
                    conflicts.append(
                        f"Bibliothèque « {entity.name} » : nom déjà utilisé par un autre UUID."
                    )
            if isinstance(entity, (Part, Package)):
                key = self.repository._owner_key(entity)
                existing = tuple(
                    self.repository._choice(r)
                    for r in session.scalars(
                        select(ChoiceRow)
                        .where(ChoiceRow.owner_key == key)
                        .order_by(ChoiceRow.asset_type)
                    )
                )
                if row and existing != choices[key]:
                    conflicts.append(f"Choix de {entity.name} : sélection locale différente.")
        target = self.publications._folder(publication.collection_id, publication.version)
        if target.exists():
            try:
                self.publications.verify(publication)
            except DomainError:
                conflicts.append(
                    "Version publiée déjà présente avec un contenu différent ou incomplet."
                )
        return tuple(conflicts)

    @staticmethod
    def _preview(
        entities: list[Entity], publication: Publication, conflicts: tuple[str, ...]
    ) -> BundlePreview:
        return BundlePreview(
            publication,
            sum(isinstance(e, Part) for e in entities),
            sum(isinstance(e, Package) for e in entities),
            sum(isinstance(e, Asset) for e in entities),
            conflicts,
        )

    def inspect(self, source: str) -> BundlePreview:
        with (
            self._archive(source) as (_, data, envelope, publication),
            Session(self.repository.engine) as session,
        ):
            entities, choices = self._projection(
                data, envelope["labels"], envelope.get("provenance", {})
            )
            return self._preview(
                entities, publication, self._conflicts(session, entities, choices, publication)
            )

    def import_bundle(self, source: str) -> BundlePreview:
        installed = False
        owned: list[tuple[Path, int]] = []
        target: Path | None = None
        try:
            with self._archive(source) as (root, data, envelope, publication):
                entities, choices = self._projection(
                    data, envelope["labels"], envelope.get("provenance", {})
                )
                target = self.publications._folder(publication.collection_id, publication.version)
                self._protect_storage()
                with Session(self.repository.engine) as session, session.begin():
                    session.execute(text("BEGIN IMMEDIATE"))
                    conflicts = self._conflicts(session, entities, choices, publication)
                    if conflicts:
                        raise DomainError(
                            "Import refusé ; conflits locaux :\n" + "\n".join(conflicts)
                        )
                    for asset in (e for e in entities if isinstance(e, Asset)):
                        assert asset.file is not None
                        dep = next(
                            d
                            for d in data["dependencies"]
                            if d["sha256"] == asset.file.sha256
                            and d["extension"] == asset.file.extension
                        )
                        captured = safe_file(root, dep["path"])
                        imported = self.store.import_file(str(captured))
                        if (imported.sha256, imported.size_bytes) != (
                            asset.file.sha256,
                            asset.file.size_bytes,
                        ):
                            raise DomainError("Dépendance modifiée pendant l'import.")
                    for entity in entities:
                        if session.get(ROWS[type(entity)], entity.id) is None:
                            self.repository._save(session, entity)
                    for entity in entities:
                        if not isinstance(entity, (Part, Package)):
                            continue
                        key = self.repository._owner_key(entity)
                        for choice in choices[key]:
                            if session.get(ChoiceRow, (key, choice.asset_type.value)) is None:
                                session.add(
                                    ChoiceRow(
                                        owner_key=key,
                                        asset_type=choice.asset_type.value,
                                        part_id=entity.id if isinstance(entity, Part) else None,
                                        package_id=entity.id
                                        if isinstance(entity, Package)
                                        else None,
                                        asset_id=choice.asset_id,
                                        reference_json="",
                                    )
                                )
                    session.flush()
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with tempfile.TemporaryDirectory(
                            prefix=".import-", dir=target.parent
                        ) as temp:
                            staging = Path(temp) / "version"
                            shutil.copytree(root, staging)

                            def confirm() -> None:
                                if self.publications._inventory(target) != [
                                    e for e in envelope["files"] if e["path"] != "COMMIT"
                                ]:
                                    raise DomainError("Version modifiée pendant l'installation.")

                            self.publications._install(staging, target, confirm, committed=True)
                            installed = True
                            owned = [(p, p.stat().st_ino) for p in target.rglob("*") if p.is_file()]
                    for asset in (e for e in entities if isinstance(e, Asset)):
                        assert asset.file is not None
                        self.store.verify(asset.file)
                    self.publications.verify(publication)
                return self._preview(entities, publication, ())
        except BaseException as error:
            if installed and target is not None:
                for path, inode in owned:
                    if not path.is_symlink() and path.exists() and path.stat().st_ino == inode:
                        path.unlink()
                for directory in sorted(
                    target.rglob("*"), key=lambda p: len(p.parts), reverse=True
                ):
                    if directory.is_dir() and not directory.is_symlink():
                        try:
                            directory.rmdir()
                        except OSError:
                            pass
                try:
                    target.rmdir()
                except OSError:
                    pass
            if isinstance(error, DomainError):
                raise
            if isinstance(error, (OSError, SQLAlchemyError, ValueError)):
                raise DomainError("Import annulé ; aucun catalogue partiel engagé.") from error
            raise

    def _protect_storage(self) -> None:
        roots = self.publications.builder.index.configuration()
        if any(
            self.publications.root.is_relative_to(Path(p).resolve())
            or self.store.root.is_relative_to(Path(p).resolve())
            for p in (roots.symbols, roots.footprints, roots.models)
            if p
        ):
            raise DomainError("Import dans une bibliothèque officielle interdit.")
