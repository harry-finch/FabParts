"""Content-addressed local store. Publication is exclusive and never overwrites."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from kipartmanager.domain.asset_files import FORMATS, AssetFile, AssetStoreError

CHUNK_SIZE = 1024 * 1024


class LocalAssetStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def import_content(self, content: bytes, filename: str) -> AssetFile:
        # Validate the simple name before using it as a temporary path.
        extension = Path(filename).suffix.lower()
        AssetFile(hashlib.sha256(content).hexdigest(), len(content), extension, filename)
        try:
            with tempfile.TemporaryDirectory(prefix="kipart-download-") as directory:
                source = Path(directory) / filename
                source.write_bytes(content)
                return self.import_file(str(source))
        except OSError as error:
            raise AssetStoreError(f"Import du téléchargement impossible : {error}.") from error

    def _path(self, file: AssetFile) -> Path:
        path = self.root / file.relative_key
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise AssetStoreError("Chemin canonique invalide dans l'Asset Store.")
        return path

    @staticmethod
    def _sync_directory(path: Path) -> None:
        if os.name == "posix":
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _copy(source: Path, destination: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as reader, destination.open("wb") as writer:
            before = os.fstat(reader.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise AssetStoreError("La source doit être un fichier régulier.")
            while chunk := reader.read(CHUNK_SIZE):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
            after = os.fstat(reader.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise AssetStoreError("La source a changé pendant la copie ; réessayer.")
        return digest.hexdigest(), size

    def import_file(self, source: str) -> AssetFile:
        source_path = Path(source)
        extension = source_path.suffix.lower()
        if extension not in FORMATS:
            raise AssetStoreError("Formats acceptés : PDF, STEP/STP, WRL, kicad_mod, kicad_sym.")
        staging: Path | None = None
        try:
            if not source_path.is_file():
                raise AssetStoreError("Source absente ou non régulière.")
            staging_dir = self.root / ".staging"
            if not staging_dir.resolve().is_relative_to(self.root):
                raise AssetStoreError("Dossier de staging invalide.")
            staging_dir.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix="import-", dir=staging_dir)
            os.close(descriptor)
            staging = Path(name)
            digest, size = self._copy(source_path, staging)
            file = AssetFile(digest, size, extension, source_path.name)
            target = self._path(file)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(staging, target)
            except FileExistsError:
                # Existing content is reused only if it still matches the identity.
                self.verify(file)
            self._sync_directory(self.root)
            self._sync_directory(self.root.parent)
            self._sync_directory(self.root / "blobs")
            self._sync_directory(target.parent)
            return file
        except OSError as error:
            raise AssetStoreError(f"Import impossible : {error.strerror or error}.") from error
        finally:
            if staging is not None:
                self._cleanup(staging)

    @staticmethod
    def _cleanup(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise AssetStoreError(
                "Impossible de nettoyer le fichier temporaire ; opération non confirmée."
            ) from error

    def verify(self, file: AssetFile) -> None:
        try:
            path = self._path(file)
            if not path.is_file():
                raise AssetStoreError("Fichier canonique absent ou non régulier.")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as reader:
                while chunk := reader.read(CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
            if size != file.size_bytes or digest.hexdigest() != file.sha256:
                raise AssetStoreError(
                    "Intégrité invalide : contenu ou taille ne correspond pas au hash."
                )
        except OSError as error:
            raise AssetStoreError(
                f"Vérification impossible : {error.strerror or error}."
            ) from error

    def retrieve(self, file: AssetFile, destination: str) -> None:
        path = Path(destination)
        staging: Path | None = None
        try:
            if path.resolve().is_relative_to(self.root):
                raise AssetStoreError("Choisir une destination en dehors de l'Asset Store.")
            if path.exists() or path.is_symlink():
                raise AssetStoreError(
                    "La destination existe déjà ; aucun fichier n'a été remplacé."
                )
            self.verify(file)
            descriptor, name = tempfile.mkstemp(prefix=".kipart-copy-", dir=path.parent)
            os.close(descriptor)
            staging = Path(name)
            digest, size = self._copy(self._path(file), staging)
            if (digest, size) != (file.sha256, file.size_bytes):
                raise AssetStoreError("Le contenu a changé pendant la restitution.")
            os.link(staging, path)
            self._sync_directory(path.parent)
        except OSError as error:
            raise AssetStoreError(f"Restitution impossible : {error.strerror or error}.") from error
        finally:
            if staging is not None:
                self._cleanup(staging)
