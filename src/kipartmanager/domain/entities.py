"""Initial catalogue and inventory model, independent of storage and Qt."""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from kipartmanager.domain.asset_files import AssetFile
    from kipartmanager.domain.asset_provenance import AssetProvenance


class DomainError(ValueError):
    """Invalid business operation."""


class ConflictError(DomainError):
    """An identity or uniqueness constraint prevents this change."""


class PartState(StrEnum):
    DRAFT = "DRAFT"
    IDENTIFIED = "IDENTIFIED"
    DEPRECATED = "DEPRECATED"


class AssetType(StrEnum):
    SYMBOL = "SYMBOL"
    FOOTPRINT = "FOOTPRINT"
    MODEL_3D = "MODEL_3D"
    DATASHEET = "DATASHEET"


class AssetOrigin(StrEnum):
    USER_PROVIDED = "USER_PROVIDED"
    KICAD_OFFICIAL = "KICAD_OFFICIAL"
    MANAGED_LIBRARY = "MANAGED_LIBRARY"
    MANUFACTURER = "MANUFACTURER"
    TRUSTED_THIRD_PARTY = "TRUSTED_THIRD_PARTY"
    GENERATED_PARAMETRIC = "GENERATED_PARAMETRIC"
    GENERATED_AI = "GENERATED_AI"


@dataclass(frozen=True, kw_only=True)
class NamedEntity:
    name: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainError("Le nom est obligatoire.")
        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True, kw_only=True)
class Part(NamedEntity):
    description: str = ""
    package_id: UUID | None = None
    asset_ids: tuple[UUID, ...] = ()
    state: PartState = PartState.DRAFT

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "asset_ids", tuple(sorted(self.asset_ids, key=str)))

    def transition(self, target: PartState) -> "Part":
        allowed = {
            PartState.DRAFT: {PartState.IDENTIFIED, PartState.DEPRECATED},
            PartState.IDENTIFIED: {PartState.DEPRECATED},
            PartState.DEPRECATED: set(),
        }
        if target not in allowed[self.state]:
            raise DomainError(f"Transition interdite : {self.state} → {target}.")
        return replace(self, state=target)


@dataclass(frozen=True, kw_only=True)
class Package(NamedEntity):
    description: str = ""
    asset_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "asset_ids", tuple(sorted(self.asset_ids, key=str)))


@dataclass(frozen=True, kw_only=True)
class Asset(NamedEntity):
    asset_type: AssetType
    origin: AssetOrigin
    source: str = ""
    file: "AssetFile | None" = None
    provenance: "AssetProvenance | None" = None
    # M1 records metadata only; no file is imported or declared valid.
    validation_state: str = field(default="UNCHECKED", init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.file is not None and self.asset_type != self.file.asset_type:
            raise DomainError("Le type d'asset ne correspond pas au format du fichier.")
        if self.provenance is not None and (
            self.file is None or self.provenance.sha256 != self.file.sha256
        ):
            raise DomainError("La provenance doit correspondre au fichier géré.")


@dataclass(frozen=True, kw_only=True)
class Inventory(NamedEntity):
    pass


@dataclass(frozen=True, kw_only=True)
class Location(NamedEntity):
    pass


@dataclass(frozen=True, kw_only=True)
class Collection(NamedEntity):
    part_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "part_ids", tuple(sorted(self.part_ids, key=str)))


@dataclass(frozen=True, kw_only=True)
class StockItem:
    part_id: UUID
    inventory_id: UUID
    quantity: int = 0
    location_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if type(self.quantity) is not int or not 0 <= self.quantity <= 2**63 - 1:
            raise DomainError("La quantité doit être un entier de 0 à 2⁶³−1.")


type Entity = Part | Package | Asset | Inventory | Location | Collection | StockItem


def require_distinct(identities: tuple[UUID, ...]) -> None:
    if len(identities) != len(set(identities)):
        raise DomainError("Une association ne peut pas être dupliquée.")


def validate_asset_associations(owner: Part | Package, assets: tuple[Asset, ...]) -> None:
    """Check asset roles on resolved domain values, without querying storage."""
    require_distinct(owner.asset_ids)
    allowed = (
        {AssetType.SYMBOL, AssetType.DATASHEET}
        if isinstance(owner, Part)
        else {AssetType.FOOTPRINT, AssetType.MODEL_3D}
    )
    if any(asset.asset_type not in allowed for asset in assets):
        raise DomainError("Type d'asset incompatible avec cette association.")
