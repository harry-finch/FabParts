"""Portable transfer outcome; inventory and qualification remain local."""

from dataclasses import dataclass

from kipartmanager.domain.publication import Publication


@dataclass(frozen=True)
class BundlePreview:
    publication: Publication
    parts: int
    packages: int
    assets: int
    conflicts: tuple[str, ...]

    @property
    def can_import(self) -> bool:
        return not self.conflicts
