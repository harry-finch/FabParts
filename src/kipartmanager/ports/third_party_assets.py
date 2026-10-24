"""Optional third-party resolver and format inspection boundaries."""

from typing import Protocol

from kipartmanager.domain.third_party_assets import (
    AssetQuery,
    ProviderState,
    ThirdPartyCandidate,
    ThirdPartyConfiguration,
    ThirdPartyDownload,
    ThirdPartySearch,
)


class ThirdPartySettings(Protocol):
    def load(self) -> ThirdPartyConfiguration: ...
    def save(self, config: ThirdPartyConfiguration) -> None: ...


class ThirdPartyProvider(Protocol):
    def state(self) -> ProviderState: ...
    def search(self, query: AssetQuery) -> ThirdPartySearch: ...
    def download(self, candidate: ThirdPartyCandidate) -> ThirdPartyDownload: ...


class CandidateInspector(Protocol):
    def inspect(self, download: ThirdPartyDownload) -> None: ...
