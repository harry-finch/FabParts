"""Explicit local candidates and one persisted choice per owner/resource role."""

from dataclasses import dataclass
from enum import IntEnum
from uuid import UUID

from kipartmanager.domain.entities import Asset, AssetType, DomainError, Package, Part
from kipartmanager.domain.kicad import KiCadReference


def allowed_roles(owner: Part | Package) -> tuple[AssetType, ...]:
    return (
        (AssetType.SYMBOL, AssetType.DATASHEET)
        if isinstance(owner, Part)
        else (AssetType.FOOTPRINT, AssetType.MODEL_3D)
    )


@dataclass(frozen=True)
class ResourceChoice:
    asset_type: AssetType
    asset_id: UUID | None = None
    reference: KiCadReference | None = None

    def __post_init__(self) -> None:
        if (self.asset_id is None) == (self.reference is None):
            raise DomainError("Un choix désigne soit un asset, soit une référence externe.")
        if self.reference is not None and self.reference.asset_type != self.asset_type:
            raise DomainError("Type de référence incompatible avec le rôle sélectionné.")

    @property
    def key(self) -> str:
        return f"asset:{self.asset_id}" if self.asset_id else self.reference_key()

    def reference_key(self) -> str:
        assert self.reference is not None
        return self.reference.key


class CandidateTier(IntEnum):
    USER = 0
    MANAGED = 1
    KICAD = 2
    REMOTE = 3
    MANUFACTURER = 4
    THIRD_PARTY = 5


@dataclass(frozen=True)
class Candidate:
    tier: CandidateTier
    choice: ResourceChoice
    name: str
    asset: Asset | None = None
    unavailable: str = ""

    @property
    def origin(self) -> str:
        return self.asset.origin.value if self.asset else "KICAD_OFFICIAL"

    @property
    def sha256(self) -> str:
        if self.asset is not None:
            return self.asset.file.sha256 if self.asset.file else ""
        assert self.choice.reference is not None
        return self.choice.reference.sha256


@dataclass(frozen=True)
class ResolutionResult:
    candidates: tuple[Candidate, ...]
    notices: tuple[str, ...] = ()
