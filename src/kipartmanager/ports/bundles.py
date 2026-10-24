"""Offline archive transport with explicit conflict inspection."""

from typing import Protocol

from kipartmanager.domain.bundles import BundlePreview
from kipartmanager.domain.publication import Publication


class BundleTransport(Protocol):
    def export(self, publication: Publication, destination: str) -> None: ...

    def inspect(self, source: str) -> BundlePreview: ...

    def import_bundle(self, source: str) -> BundlePreview: ...
