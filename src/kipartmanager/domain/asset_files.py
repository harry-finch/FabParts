"""Portable file identity and import-format rules; no filesystem dependencies."""

from dataclasses import dataclass

from kipartmanager.domain.entities import AssetType, DomainError

FORMATS = {
    ".pdf": AssetType.DATASHEET,
    ".step": AssetType.MODEL_3D,
    ".stp": AssetType.MODEL_3D,
    ".wrl": AssetType.MODEL_3D,
    ".kicad_mod": AssetType.FOOTPRINT,
    ".kicad_sym": AssetType.SYMBOL,
}


class AssetStoreError(DomainError):
    """File access, integrity or managed-store operation failed."""


@dataclass(frozen=True)
class AssetFile:
    sha256: str
    size_bytes: int
    extension: str
    original_name: str
    symbol_name: str = ""

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise DomainError("Empreinte SHA-256 invalide.")
        if type(self.size_bytes) is not int or not 0 < self.size_bytes <= 2**63 - 1:
            raise DomainError("Le fichier doit être non vide et sa taille valide.")
        if not isinstance(self.symbol_name, str):
            raise DomainError("Le nom du symbole doit être du texte.")
        if self.symbol_name and (self.extension != ".kicad_sym" or "\x00" in self.symbol_name):
            raise DomainError("Entrée de symbole incompatible avec le fichier.")
        if self.extension not in FORMATS:
            raise DomainError("Format de fichier non pris en charge.")
        if (
            not self.original_name
            or any(char in self.original_name for char in "/\\\x00")
            or self.original_name in {".", ".."}
        ):
            raise DomainError("Le nom original doit être un nom de fichier simple.")

    @property
    def asset_type(self) -> AssetType:
        return FORMATS[self.extension]

    @property
    def relative_key(self) -> str:
        return f"blobs/{self.sha256[:2]}/{self.sha256}"
