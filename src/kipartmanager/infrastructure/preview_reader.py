"""Bounded, verified byte snapshots; no writes to managed or official sources."""

import hashlib
import os
import stat
from pathlib import Path

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_preview import drawings
from kipartmanager.infrastructure.model_preview import model_mesh
from kipartmanager.ports.previews import PreviewContent


class LocalPreviewReader:
    def __init__(self, store: LocalAssetStore, index: LocalKiCadIndex) -> None:
        self.store, self.index = store, index

    @staticmethod
    def snapshot(path: Path, digest: str, kind: AssetType) -> bytes:
        limit = (128 if kind is AssetType.DATASHEET else 64) * 1024 * 1024
        try:
            with path.open("rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise DomainError("La ressource doit être un fichier régulier.")
                content = stream.read(limit + 1)
        except OSError as error:
            raise DomainError(f"Ressource indisponible : {error}.") from error
        if len(content) > limit:
            raise DomainError(
                f"Aperçu limité aux fichiers de {limit // (1024 * 1024)} Mio maximum."
            )
        if hashlib.sha256(content).hexdigest() != digest:
            raise DomainError("Fichier modifié ou corrompu : aperçu refusé. Vérifiez ou réindexez.")
        return content

    @staticmethod
    def decode(content: bytes, kind: AssetType, selected: str = "") -> PreviewContent:
        if kind is AssetType.MODEL_3D:
            return PreviewContent(mesh=model_mesh(content))
        if kind is AssetType.DATASHEET:
            if not content.startswith(b"%PDF-"):
                raise DomainError("En-tête PDF non reconnu.")
            return PreviewContent(pdf=content)
        if kind not in (AssetType.SYMBOL, AssetType.FOOTPRINT):
            raise DomainError("Ce format n’a pas encore de viewer.")
        try:
            return PreviewContent(drawings=drawings(content.decode("utf-8"), kind, selected))
        except UnicodeError as error:
            raise DomainError("Fichier KiCad non UTF-8.") from error

    def managed(self, file: AssetFile) -> PreviewContent:
        content = self.snapshot(self.store._path(file), file.sha256, file.asset_type)
        if len(content) != file.size_bytes:
            raise DomainError("La taille du fichier ne correspond pas à son identité.")
        return self.decode(content, file.asset_type, file.symbol_name)

    def official(self, reference: KiCadReference) -> PreviewContent:
        roots = self.index.configuration()
        folder = {
            AssetType.SYMBOL: roots.symbols,
            AssetType.FOOTPRINT: roots.footprints,
            AssetType.MODEL_3D: roots.models,
        }[reference.asset_type]
        if not folder:
            raise DomainError("Dossier KiCad non configuré.")
        root = Path(folder).expanduser().resolve()
        path = root / reference.relative_path
        if not path.resolve().is_relative_to(root):
            raise DomainError("La référence sort du dossier KiCad.")
        content = self.snapshot(path, reference.sha256, reference.asset_type)
        return self.decode(content, reference.asset_type, reference.name)
