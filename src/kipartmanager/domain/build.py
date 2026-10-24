"""Current-collection build inputs and output identities, without persistence."""

import re
from dataclasses import dataclass
from uuid import UUID

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import AssetType
from kipartmanager.domain.resolution import ResourceChoice


def library_name(name: str, identity: UUID) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:48].strip("_") or "Collection"
    return f"KPM_{stem}_{identity.hex}"


@dataclass(frozen=True)
class BuildResource:
    choice: ResourceChoice
    file: AssetFile | None
    origin: str
    source: str

    @property
    def asset_type(self) -> AssetType:
        return self.choice.asset_type


@dataclass(frozen=True)
class BuildPart:
    identity: UUID
    name: str
    package_id: UUID
    resources: tuple[BuildResource, ...]

    @property
    def symbol_name(self) -> str:
        return f"P_{self.identity.hex}"

    @property
    def footprint_name(self) -> str:
        return f"F_{self.package_id.hex}"


@dataclass(frozen=True)
class BuildPlan:
    collection_id: UUID
    collection_name: str
    fingerprint: str
    parts: tuple[BuildPart, ...]

    @property
    def library(self) -> str:
        return library_name(self.collection_name, self.collection_id)


@dataclass(frozen=True)
class BuildResult:
    destination: str
    library: str
    symbols: int
    footprints: int
    files: tuple[str, ...]
