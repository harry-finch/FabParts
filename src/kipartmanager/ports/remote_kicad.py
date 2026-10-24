"""Optional official provider and machine-local configuration contracts."""

from typing import Protocol

from kipartmanager.domain.entities import AssetType
from kipartmanager.domain.remote_kicad import (
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteSearch,
)


class RemoteProvider(Protocol):
    def search(self, revision: str, kind: AssetType, library: str, query: str) -> RemoteSearch: ...
    def download(self, candidate: RemoteCandidate) -> RemoteDownload: ...


class RemoteSettings(Protocol):
    def load(self) -> RemoteConfiguration: ...
    def save(self, config: RemoteConfiguration) -> None: ...
