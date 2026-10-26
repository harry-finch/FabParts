"""Additional read-only links for discovery, separate from M5 inspection snapshots."""

from typing import Protocol

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.ports.validation import ResourceProbe


class DiscoveryProbe(ResourceProbe, Protocol):
    def model_links(
        self, file: AssetFile | None, reference: KiCadReference | None
    ) -> tuple[str, ...]: ...
