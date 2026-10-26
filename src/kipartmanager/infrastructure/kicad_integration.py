"""Dedicated immutable global copies and a recoverable two-table transaction.

No current catalogue, official library write, or M7 writer modification.
"""

import base64
import hashlib
import json
import os
import secrets
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from kipartmanager.domain.entities import DomainError
from kipartmanager.domain.publication import Publication
from kipartmanager.infrastructure.atomic_tables import replace as replace_file
from kipartmanager.infrastructure.ingestion_sandbox import checked_root
from kipartmanager.infrastructure.kicad_parser import Node, parse
from kipartmanager.infrastructure.kicad_tables import LIMIT, NAMES, Table
from kipartmanager.infrastructure.kicad_writer import serialize
from kipartmanager.infrastructure.publications import LocalPublications, digest_file, safe_file
from kipartmanager.infrastructure.workspace_backup import atomic_json, sync_dir

__all__ = ["LocalKiCadIntegration", "replace_file"]

FORMAT = "fabparts-kicad-integration/1"
# Official release file-format ceilings; newer sources are refused, never downgraded.
FORMAT_LIMITS = {
    "6.0": ("20211014", "20211014"),
    "7.0": ("20220914", "20221018"),
    "8.0": ("20231120", "20240108"),
    "9.0": ("20241209", "20241229"),
    "10.0": ("20251024", "20260206"),
}


def read(path: Path) -> bytes | None:
    if path != path.absolute().resolve() or path.is_symlink():
        raise DomainError("UNSAFE_PATH: symbolic path refused")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16 * LIMIT or path.stat().st_nlink != 1:
        raise DomainError("UNSAFE_PATH: regular private file required")
    return path.read_bytes()


def pack(value: bytes | None) -> str | None:
    return base64.b64encode(value).decode() if value is not None else None


def unpack(value: str | None) -> bytes | None:
    return base64.b64decode(value, validate=True) if value is not None else None


def inventory(folder: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for p in sorted(folder.rglob("*")):
        if p.is_symlink():
            raise DomainError("UNSAFE_PATH: installation symlink")
        if p.is_file() and p.name not in {"INSTALLATION.json", "READY"}:
            digest, size = digest_file(p)
            result[p.relative_to(folder).as_posix()] = {"sha256": digest, "size": size}
    return result


def adapt(node: Node, destination: Path, old: str, nickname: str) -> None:
    for i, value in enumerate(node.atoms):
        if value.startswith("${KIPRJMOD}/"):
            relative = value[len("${KIPRJMOD}/") :]
            target = safe_file(destination, relative)
            if not target.exists():
                raise DomainError("UNRESOLVED_PATH: missing installed dependency")
            node.atoms[i] = str(target)
            node.quoted.add(i)
    if len(node.atoms) >= 3 and node.atoms[:2] == ["property", "Footprint"]:
        if not node.atoms[2].startswith(old + ":"):
            raise DomainError("UNRESOLVED_PATH: unexpected footprint nickname")
        node.atoms[2] = nickname + node.atoms[2][len(old) :]
    for child in node.children:
        adapt(child, destination, old, nickname)


class LocalKiCadIntegration:
    def __init__(
        self,
        data_root: Path,
        publications: LocalPublications,
        config_root: Path | None,
        versions: tuple[str, ...] = (),
    ) -> None:
        self.data_root = data_root.resolve()
        self.root = self.data_root / "config/kicad-integration"
        self.publications = publications
        self.config_root = config_root
        self.versions = tuple(
            sorted({v for v in versions if v in FORMAT_LIMITS}, key=lambda v: int(v.split(".")[0]))
        )
        self.viewed: dict[str, dict[str, Any]] = {}

    def target(self, target: str) -> Path:
        if self.config_root is None or target not in self.versions:
            raise DomainError("KICAD_UNAVAILABLE: select an installed supported KiCad")
        path = checked_root(self.config_root / target)
        roots = self.publications.builder.index.configuration()
        for value in (roots.symbols, roots.footprints, roots.models):
            if value and (
                path.is_relative_to(Path(value).resolve())
                or self.root.is_relative_to(Path(value).resolve())
            ):
                raise DomainError("UNSAFE_PATH: installation inside source libraries refused")
        return path

    def _global(self, target: str) -> Path:
        return self.target(target) / ".fabparts"

    def _state(self, target: str) -> tuple[bytes | None, dict[str, Any]]:
        folder = self._global(target)
        raw = read(folder / "state.json")
        if folder.exists() and read(folder / "OWNER") != FORMAT.encode():
            raise DomainError("OWNERSHIP_REQUIRED: unrecognized .fabparts folder")
        state = (
            json.loads(raw)
            if raw
            else {"format": FORMAT, "active": {}, "operations": [], "pending": None}
        )
        if state.get("format") != FORMAT or not isinstance(state.get("active"), dict):
            raise DomainError("INVALID_STATE: integration journal unreadable")
        return raw, state

    def _tables(self, target: str) -> tuple[bytes | None, bytes | None]:
        folder = self.target(target)
        values = tuple(read(folder / name) for name in NAMES)
        for i, value in enumerate(values):
            Table.read(value, i, target)
        return values[0], values[1]

    def _mirror(self, target: str, collection: str) -> Path:
        return self.root / "mirrors" / target / (collection + ".json")

    def _copy(self, path: Path) -> dict[str, Any]:
        # A restored generation may inspect retained copies in its same workspace home.
        allowed = self.data_root
        if self.data_root.parent.name == "workspaces":
            allowed = self.data_root.parent
        if not path.is_relative_to(allowed) or "/config/kicad-integration/installed/" not in str(
            path
        ):
            raise DomainError("UNSAFE_PATH: installation outside managed workspace")
        raw = read(path / "INSTALLATION.json")
        ready = read(path / "READY")
        if raw is None or ready != hashlib.sha256(raw).hexdigest().encode():
            raise DomainError("INSTALLATION_CORRUPT: missing seal")
        data = json.loads(raw)
        if (
            data.get("format") != FORMAT
            or data.get("path") != str(path)
            or inventory(path) != data["files"]
        ):
            raise DomainError("INSTALLATION_CORRUPT: installed bytes changed")
        for i, name in enumerate(NAMES):
            table = Table.read(read(path / name), i)
            if nickname_uri := table.entries.get(data["nickname"]):
                if nickname_uri[2] != data["uris"][i]:
                    raise DomainError("UNRESOLVED_PATH: installation table URI")
            else:
                raise DomainError("UNRESOLVED_PATH: installation table nickname")
        for file in path.rglob("*"):
            if file.suffix in {".kicad_sym", ".kicad_mod"}:
                text = file.read_text()
                if "${KIPRJMOD}" in text:
                    raise DomainError("UNRESOLVED_PATH: project variable remains")
                self._references(parse(text), path, data["nickname"])
        return dict(data)

    def _references(self, node: Node, path: Path, nickname: str) -> None:
        if node.atoms and node.atoms[0] == "model":
            if (
                len(node.atoms) < 2
                or not Path(node.atoms[1]).is_relative_to(path)
                or not Path(node.atoms[1]).is_file()
            ):
                raise DomainError("UNRESOLVED_PATH: installed model")
        if len(node.atoms) >= 3 and node.atoms[:2] == ["property", "Datasheet"] and node.atoms[2]:
            p = Path(node.atoms[2])
            if not p.is_relative_to(path) or not p.is_file():
                raise DomainError("UNRESOLVED_PATH: installed datasheet")
        if len(node.atoms) >= 3 and node.atoms[:2] == ["property", "Footprint"]:
            value = node.atoms[2]
            if not value.startswith(nickname + ":") or not any(
                path.glob("*.pretty/" + value.split(":", 1)[1] + ".kicad_mod")
            ):
                raise DomainError("UNRESOLVED_PATH: installed footprint")
        for child in node.children:
            self._references(child, path, nickname)

    def _install(self, publication: Publication, target: str) -> dict[str, Any]:
        version_root = (
            self.root / "installed" / str(publication.collection_id) / f"v{publication.version:06d}"
        )
        for marker in sorted(version_root.glob("*/READY")):
            try:
                existing = self._copy(marker.parent)
                if (
                    existing["manifest_sha256"] == publication.manifest_sha256
                    and existing["target"] == target
                ):
                    return existing
            except (DomainError, OSError, ValueError, KeyError):
                # Retain changed or restored copies; create a distinct verified copy only
                # following the user's explicit activation preparation.
                continue
        folder = (
            self.root
            / "installed"
            / str(publication.collection_id)
            / f"v{publication.version:06d}"
            / uuid4().hex
        )
        folder.parent.mkdir(parents=True, exist_ok=True)
        # Keep M7's public destination protections: reconstruct outside all data first.
        with tempfile.TemporaryDirectory(prefix="fabparts-global-") as temporary:
            staged = Path(temporary) / "build"
            result = self.publications.rebuild(publication, str(staged))
            shutil.copytree(staged, folder)
        nickname = "FabParts_" + publication.collection_id.hex
        # The fresh dedicated copy is not exposed in any table until sealed and checked.
        for path in folder.rglob("*"):
            if path.suffix in {".kicad_sym", ".kicad_mod"} or path.name in NAMES:
                node = parse(path.read_text())
                if path.suffix in {".kicad_sym", ".kicad_mod"}:
                    limit = FORMAT_LIMITS[target][0 if path.suffix == ".kicad_sym" else 1]
                    if node.value("version") > limit:
                        raise DomainError(
                            "KICAD_VERSION: source format requires a newer KiCad target"
                        )
                adapt(node, folder, result.library, nickname)
                if path.name in NAMES:
                    for entry in node.children_named("lib"):
                        entry.children_named("name")[0].atoms[1] = nickname
                path.write_text(serialize(node) + "\n")
        (folder / "UTILISATION.txt").write_text(
            "FabParts — global installation copy. Do not edit.\n"
        )
        data = {
            "format": FORMAT,
            "collection": str(publication.collection_id),
            "name": publication.collection_name[:256],
            "version": publication.version,
            "manifest_sha256": publication.manifest_sha256,
            "nickname": nickname,
            "path": str(folder),
            "uris": [
                str(folder / (result.library + ".kicad_sym")),
                str(folder / (result.library + ".pretty")),
            ],
            "files": inventory(folder),
            "target": target,
        }
        atomic_json(folder / "INSTALLATION.json", data)
        # Seal the exact bytes written by atomic_json.
        seal = hashlib.sha256((folder / "INSTALLATION.json").read_bytes()).hexdigest().encode()
        with (folder / "READY").open("xb") as stream:
            stream.write(seal)
            stream.flush()
            os.fsync(stream.fileno())
        for file in folder.rglob("*"):
            if file.is_file():
                with file.open("rb") as stream:
                    os.fsync(stream.fileno())
        sync_dir(folder)
        return self._copy(folder)

    def _token(self, value: dict[str, Any]) -> str:
        token = secrets.token_hex(24)
        self.viewed[token] = value
        while len(self.viewed) > 16:
            self.viewed.pop(next(iter(self.viewed)))
        return token

    def status(self, collection_id: UUID, target: str = "") -> dict[str, Any]:
        targets = [
            {"id": v, "configuration": str(self.config_root / v)}
            for v in self.versions
            if self.config_root
        ]
        target = target or (self.versions[-1] if self.versions else "")
        publication_error = ""
        try:
            latest = max(
                (p.version for p in self.publications.list_publications(collection_id)),
                default=None,
            )
        except DomainError as error:
            latest = None
            publication_error = str(error)[:2048]
        base: dict[str, Any] = {
            "targets": targets,
            "target": target,
            "latest": latest,
            "publication_error": publication_error,
            "active": None,
            "previous": None,
            "state": "UNCONFIGURED",
            "operations": [],
            "tables": [],
        }
        if not target:
            return base
        try:
            _, state = self._state(target)
            tables = self._tables(target)
            active = state["active"].get(str(collection_id))
            previous = active.get("previous") if active else None
            base["installed"] = [
                {
                    "id": key,
                    "name": value.get("name", value["nickname"]),
                    "version": value["version"],
                }
                for key, value in list(state["active"].items())[:50]
            ]
            base.update(
                active=active["version"] if active else None,
                previous=previous,
                tables=[
                    {"name": name, "present": value is not None}
                    for name, value in zip(NAMES, tables, strict=True)
                ],
                operations=[
                    {
                        "id": op["id"],
                        "version": op["version"],
                        "collection": op["collection"],
                        "date": op["date"],
                    }
                    for op in [
                        o for o in state["operations"] if o["collection"] == str(collection_id)
                    ][-20:][::-1]
                ],
            )
            if state["pending"]:
                return base | {"state": "RECOVERY_REQUIRED"}
            if active:
                for i, raw in enumerate(tables):
                    if not Table.read(raw, i).owns(active["nickname"], active["entries"][i]):
                        return base | {"state": "INTERVENTION_REQUIRED"}
                mirror = read(self._mirror(target, str(collection_id)))
                expected = {"operation": active["operation"], "workspace": str(self.data_root)}
                if mirror is None or json.loads(mirror) != expected:
                    return base | {"state": "RECONCILE_REQUIRED"}
                self._copy(Path(active["path"]))
                if publication_error:
                    return base | {"state": "SOURCE_UNAVAILABLE"}
                return base | {
                    "state": "UPDATE_AVAILABLE"
                    if latest and latest > active["version"]
                    else "CURRENT"
                }
            return base
        except (DomainError, OSError, ValueError, KeyError, TypeError) as error:
            return base | {"state": "ERROR", "error": str(error)[:2048]}

    def prepare(self, publication: Publication, target: str) -> dict[str, Any]:
        raw, state = self._state(target)
        if state["pending"]:
            raise DomainError("RECOVERY_REQUIRED: restore the saved tables first")
        before = self._tables(target)
        active = state["active"].get(str(publication.collection_id))
        self.publications.verify(publication)
        copy = self._install(publication, target)
        after = []
        for i, value in enumerate(before):
            after.append(
                Table.read(value, i).updated(
                    i, copy["nickname"], copy["uris"][i], active["entries"][i] if active else None
                )
            )
        item = {
            "collection": str(publication.collection_id),
            "target": target,
            "publication": publication,
            "before": before,
            "after": tuple(after),
            "state_raw": raw,
            "state": state,
            "copy": copy,
            "action": "activate",
        }
        return {
            "handle": self._token(item),
            "version": publication.version,
            "active": active["version"] if active else None,
            "nickname": copy["nickname"],
            "uris": copy["uris"],
            "tables": list(NAMES),
            "target": target,
            "collection_name": publication.collection_name[:256],
            "reconcile": self.status(publication.collection_id, target)["state"]
            == "RECONCILE_REQUIRED",
        }

    @contextmanager
    def _lock(self, target: str) -> Any:
        import fcntl

        folder = self._global(target)
        folder.parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            folder.mkdir(mode=0o700)
            with (folder / "OWNER").open("xb") as stream:
                stream.write(FORMAT.encode())
                stream.flush()
                os.fsync(stream.fileno())
            sync_dir(folder)
        if read(folder / "OWNER") != FORMAT.encode():
            raise DomainError("OWNERSHIP_REQUIRED: unrecognized metadata")
        lock = folder / "lock"
        if lock.is_symlink():
            raise DomainError("UNSAFE_PATH: linked lock")
        with lock.open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise DomainError("BUSY: another installation is in progress") from error
            yield

    def _take(self, collection_id: UUID, target: str, handle: str, action: str) -> dict[str, Any]:
        item = self.viewed.pop(handle, None)
        if not item or (item["collection"], item["target"], item["action"]) != (
            str(collection_id),
            target,
            action,
        ):
            raise DomainError("SUMMARY_CHANGED: review the operation again")
        return item

    def activate(self, collection_id: UUID, target: str, handle: str) -> dict[str, Any]:
        item = self._take(collection_id, target, handle, "activate")
        with self._lock(target):
            raw, state = self._state(target)
            if raw != item["state_raw"] or self._tables(target) != item["before"]:
                raise DomainError("TABLE_CHANGED: external changes since preview")
            self.publications.verify(item["publication"])
            copy = self._copy(Path(item["copy"]["path"]))
            operation = uuid4().hex
            active = dict(copy)
            active["entries"] = [
                Table.read(value, i).entry(copy["nickname"])
                for i, value in enumerate(item["after"])
            ]
            active["operation"] = operation
            old = state["active"].get(str(collection_id))
            active["previous"] = (
                old["version"]
                if old and old["version"] != copy["version"]
                else old.get("previous")
                if old
                else None
            )
            next_state = json.loads(json.dumps(state))
            next_state["active"][str(collection_id)] = active
            next_state["operations"].append(
                {
                    "id": operation,
                    "date": datetime.now(UTC).isoformat(),
                    "collection": str(collection_id),
                    "version": copy["version"],
                }
            )
            next_state["pending"] = None
            journal = {
                "format": FORMAT,
                "before": [pack(v) for v in item["before"]],
                "after": [pack(v) for v in item["after"]],
                "previous_state": state,
                "next_state": next_state,
            }
            folder = self._global(target) / "operations" / operation
            folder.mkdir(parents=True)
            atomic_json(folder / "journal.json", journal)
            content = read(folder / "journal.json")
            assert content is not None
            with (folder / "SEALED").open("xb") as stream:
                stream.write(hashlib.sha256(content).hexdigest().encode())
                stream.flush()
                os.fsync(stream.fileno())
            sync_dir(folder)
            # Read back and verify the exact two-table backup before any table mutation.
            if self._journal(target, operation) != journal:
                raise DomainError("BACKUP_FAILED: table backup mismatch")
            retained = self.root / "transactions" / target / operation
            retained.mkdir(parents=True)
            atomic_json(retained / "journal.json", journal)
            if self._read_json(retained / "journal.json") != journal:
                raise DomainError("BACKUP_FAILED: workspace journal mismatch")
            pending = dict(state)
            pending["pending"] = operation
            atomic_json(self._global(target) / "state.json", pending)
            expected = list(item["before"])
            for i, name in enumerate(NAMES):
                if self._tables(target) != tuple(expected):
                    raise DomainError("TABLE_CHANGED: external change during installation")
                replace_file(
                    self.target(target) / name,
                    expected[i],
                    item["after"][i],
                    folder / f"capture-{i}-{uuid4().hex}",
                )
                expected[i] = item["after"][i]
            if self._tables(target) != item["after"]:
                raise DomainError("TABLE_CHANGED: installed tables changed")
            self._copy(Path(copy["path"]))
            atomic_json(self._global(target) / "state.json", next_state)
            mirror = self._mirror(target, str(collection_id))
            mirror.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(mirror, {"operation": operation, "workspace": str(self.data_root)})
        return self.status(collection_id, target)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        raw = read(path)
        if raw is None:
            raise DomainError("INVALID_JOURNAL: metadata missing")
        return dict(json.loads(raw))

    def _journal(self, target: str, operation: str) -> dict[str, Any]:
        if len(operation) != 32 or any(c not in "0123456789abcdef" for c in operation):
            raise DomainError("INVALID_JOURNAL: operation identity")
        folder = self._global(target) / "operations" / operation
        raw = read(folder / "journal.json")
        if raw is None or read(folder / "SEALED") != hashlib.sha256(raw).hexdigest().encode():
            raise DomainError("INVALID_JOURNAL: backup seal mismatch")
        data = json.loads(raw)
        if data.get("format") != FORMAT or len(data["before"]) != 2 or len(data["after"]) != 2:
            raise DomainError("INVALID_JOURNAL: backup schema")
        return dict(data)

    @staticmethod
    def _check_recovery_collection(collection_id: UUID, journal: dict[str, Any]) -> None:
        owner = journal["next_state"]["operations"][-1]["collection"]
        if owner != str(collection_id):
            raise DomainError(
                "RECOVERY_COLLECTION_MISMATCH: interrupted operation belongs to another collection"
            )

    def recovery(self, collection_id: UUID, target: str) -> dict[str, Any]:
        raw, state = self._state(target)
        if not state["pending"]:
            raise DomainError("NO_RECOVERY: no interrupted operation")
        journal = self._journal(target, state["pending"])
        self._check_recovery_collection(collection_id, journal)
        self._recoverable(target, journal, state["pending"])
        item = {
            "collection": str(collection_id),
            "target": target,
            "action": "recover",
            "state_raw": raw,
            "operation": state["pending"],
            "journal": journal,
        }
        return {
            "handle": self._token(item),
            "target": target,
            "tables": list(NAMES),
            "action": "restore_previous_tables",
            "version": journal["next_state"]["operations"][-1]["version"],
            "collection_name": journal["next_state"]["active"][
                journal["next_state"]["operations"][-1]["collection"]
            ].get("name", "FabParts"),
        }

    def _recoverable(self, target: str, journal: dict[str, Any], operation: str) -> None:
        for i, name in enumerate(NAMES):
            for capture in (self._global(target) / "operations" / operation).glob(f"capture-{i}-*"):
                if read(capture) not in (unpack(journal["before"][i]), unpack(journal["after"][i])):
                    raise DomainError("RECOVERY_CONFLICT: concurrent captured bytes retained")
            current = read(self.target(target) / name)
            if current not in (unpack(journal["before"][i]), unpack(journal["after"][i])):
                raise DomainError(
                    "RECOVERY_CONFLICT: external table changes; manual intervention required"
                )

    def recover(self, collection_id: UUID, target: str, handle: str) -> dict[str, Any]:
        item = self._take(collection_id, target, handle, "recover")
        with self._lock(target):
            raw, state = self._state(target)
            if raw != item["state_raw"]:
                raise DomainError("SUMMARY_CHANGED: recovery changed")
            journal = self._journal(target, state["pending"])
            self._check_recovery_collection(collection_id, journal)
            if journal != item["journal"]:
                raise DomainError("INVALID_JOURNAL: backup changed")
            self._recoverable(target, journal, state["pending"])
            for i, name in enumerate(NAMES):
                self._recoverable(target, journal, state["pending"])
                path = self.target(target) / name
                replace_file(
                    path,
                    read(path),
                    unpack(journal["before"][i]),
                    self._global(target)
                    / "operations"
                    / state["pending"]
                    / f"capture-{i}-{uuid4().hex}",
                )
            atomic_json(self._global(target) / "state.json", journal["previous_state"])
        return self.status(collection_id, target)

    def verify(self, collection_id: UUID, target: str) -> dict[str, Any]:
        result = self.status(collection_id, target)
        if result["state"] not in {"CURRENT", "UPDATE_AVAILABLE", "RECONCILE_REQUIRED"}:
            raise DomainError("INSTALLATION_INVALID: tables or installed files need intervention")
        _, state = self._state(target)
        self._copy(Path(state["active"][str(collection_id)]["path"]))
        return result | {"verified": True, "checked_at": datetime.now(UTC).isoformat()}
