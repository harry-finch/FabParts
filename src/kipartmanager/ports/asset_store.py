"""Managed-file operations via opaque source/destination locators."""

from typing import Protocol

from kipartmanager.domain.asset_files import AssetFile


class AssetStore(Protocol):
    def import_file(self, source: str) -> AssetFile: ...

    def import_content(self, content: bytes, filename: str) -> AssetFile: ...

    def verify(self, file: AssetFile) -> None: ...

    def retrieve(self, file: AssetFile, destination: str) -> None: ...
