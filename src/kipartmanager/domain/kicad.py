"""Portable external references, separate from managed catalogue assets."""

from dataclasses import dataclass
from urllib.parse import quote

from kipartmanager.domain.entities import AssetOrigin, AssetType, DomainError


class KiCadError(DomainError):
    pass


@dataclass(frozen=True)
class LibraryRoots:
    symbols: str = ""
    footprints: str = ""
    models: str = ""


@dataclass(frozen=True, kw_only=True)
class KiCadReference:
    asset_type: AssetType
    library: str
    name: str
    relative_path: str
    sha256: str
    description: str = ""
    keywords: str = ""
    format_version: str = ""
    extends: str = ""

    def __post_init__(self) -> None:
        if self.asset_type not in {AssetType.SYMBOL, AssetType.FOOTPRINT, AssetType.MODEL_3D}:
            raise KiCadError("Type de référence KiCad invalide.")
        if not self.library or not self.name:
            raise KiCadError("Identité KiCad vide.")
        if ":" in self.library or ":" in self.name:
            raise KiCadError("Deux-points interdits dans une identité KiCad.")
        if (
            not self.relative_path
            or self.relative_path.startswith("/")
            or "\\" in self.relative_path
            or ":" in self.relative_path
            or any(part in {"", ".", ".."} for part in self.relative_path.split("/"))
        ):
            raise KiCadError("Chemin de référence non portable.")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise KiCadError("SHA-256 invalide.")

    @property
    def identifier(self) -> str:
        if self.asset_type is AssetType.MODEL_3D:
            return self.relative_path
        return f"{self.library}:{self.name}"

    @property
    def key(self) -> str:
        return f"kicad:{self.asset_type.value}:{quote(self.identifier, safe='')}"

    @property
    def origin(self) -> AssetOrigin:
        return AssetOrigin.KICAD_OFFICIAL


@dataclass(frozen=True)
class IndexIssue:
    source: str
    message: str


@dataclass(frozen=True)
class IndexReport:
    count: int
    issues: tuple[IndexIssue, ...] = ()
