"""Unselected third-party candidates; no vendor API assumptions or transport code."""

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from kipartmanager.domain.asset_provenance import AssetProvenance, Redistribution
from kipartmanager.domain.entities import AssetOrigin, AssetType, DomainError


class ProviderState(StrEnum):
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    CONTRACT_REQUIRED = "contract_required"
    READY = "ready"


@dataclass(frozen=True)
class ThirdPartyConfiguration:
    enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise DomainError("Activation du fournisseur invalide.")


@dataclass(frozen=True)
class AssetQuery:
    mpn: str
    manufacturer: str
    asset_type: AssetType

    def __post_init__(self) -> None:
        if not self.mpn.strip() or len(self.mpn) > 256 or len(self.manufacturer) > 256:
            raise DomainError("Saisir un MPN exact (256 caractères maximum).")
        if any(ord(c) < 32 for c in self.mpn + self.manufacturer):
            raise DomainError("Identification de recherche invalide.")
        if self.asset_type not in {AssetType.SYMBOL, AssetType.FOOTPRINT, AssetType.MODEL_3D}:
            raise DomainError("Recherche tierce limitée aux symboles, footprints et modèles 3D.")


@dataclass(frozen=True)
class ThirdPartyCandidate:
    provider: str
    provider_id: str
    asset_type: AssetType
    name: str
    mpn: str
    manufacturer: str
    filename: str
    source_url: str
    resolved_at: str
    package: str = ""
    symbol_name: str = ""
    expected_sha256: str = ""
    license_name: str = ""
    license_url: str = ""
    attribution: str = ""
    redistribution: Redistribution = Redistribution.UNKNOWN
    rights_reference: str = ""

    def __post_init__(self) -> None:
        extension = self.extension
        formats = {
            AssetType.SYMBOL: {".kicad_sym"},
            AssetType.FOOTPRINT: {".kicad_mod"},
            AssetType.MODEL_3D: {".step", ".stp", ".wrl"},
        }
        if extension not in formats.get(self.asset_type, set()) or not self.name.strip():
            raise DomainError("Type ou format de candidat non pris en charge.")
        if self.filename in {".", ".."} or any(c in self.filename for c in "/\\:\x00\n\r"):
            raise DomainError("Nom de fichier candidat invalide.")
        if self.expected_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise DomainError("Empreinte de candidat invalide.")
        if self.asset_type is not AssetType.SYMBOL and self.symbol_name:
            raise DomainError("Entrée de symbole incompatible.")
        self.provenance("0" * 64, self.resolved_at)

    @property
    def extension(self) -> str:
        return "." + self.filename.rsplit(".", 1)[-1].lower()

    @property
    def origin(self) -> AssetOrigin:
        return AssetOrigin.TRUSTED_THIRD_PARTY

    def provenance(self, digest: str, imported_at: str) -> AssetProvenance:
        return AssetProvenance(
            self.provider,
            self.provider_id,
            self.source_url,
            self.resolved_at,
            imported_at,
            digest,
            self.mpn,
            self.manufacturer,
            self.package,
            self.license_name,
            self.license_url,
            self.attribution,
            self.redistribution,
            self.rights_reference,
        )


@dataclass(frozen=True)
class ThirdPartySearch:
    query: AssetQuery
    candidates: tuple[ThirdPartyCandidate, ...] = ()
    notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThirdPartyDownload:
    candidate: ThirdPartyCandidate
    content: bytes

    def __post_init__(self) -> None:
        if not 0 < len(self.content) <= 32 * 1024 * 1024:
            raise DomainError("Téléchargement vide ou supérieur à 32 Mio.")
        if self.candidate.expected_sha256 and self.sha256 != self.candidate.expected_sha256:
            raise DomainError("Hash différent du candidat ; aucun asset importé.")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()
