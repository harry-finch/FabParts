"""Explicit remote operations, independent of the local resolver and its choices."""

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType
from kipartmanager.domain.remote_kicad import (
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteError,
    RemoteSearch,
    simple_name,
    verify_download,
)
from kipartmanager.ports.remote_kicad import RemoteProvider, RemoteSettings


class RemoteLibraries:
    def __init__(
        self,
        settings: RemoteSettings,
        imports: AssetImports,
        provider: RemoteProvider | None = None,
    ) -> None:
        self.settings, self.imports, self.provider = settings, imports, provider

    def configuration(self) -> RemoteConfiguration:
        return self.settings.load()

    def configure(self, config: RemoteConfiguration) -> None:
        self.settings.save(config)

    def require_enabled(self) -> RemoteConfiguration:
        config = self.configuration()
        if not config.enabled:
            raise RemoteError(
                "Recherche distante désactivée ; les ressources locales restent accessibles."
            )
        if self.provider is None:
            raise RemoteError(
                "Adaptateur distant absent ; les ressources locales restent accessibles."
            )
        return config

    def search(self, kind: AssetType, library: str, query: str) -> RemoteSearch:
        config = self.require_enabled()
        if not simple_name(library.strip()):
            raise RemoteError(
                "Saisir une bibliothèque précise, par exemple Device ou Resistor_SMD."
            )
        assert self.provider is not None
        return self.provider.search(config.revision, kind, library.strip(), query.strip())

    def download(self, candidate: RemoteCandidate) -> RemoteDownload:
        config = self.require_enabled()
        if config.revision != candidate.revision:
            raise RemoteError("La révision configurée a changé ; relancer la recherche.")
        assert self.provider is not None
        return self.provider.download(candidate)

    def import_download(self, download: RemoteDownload) -> Asset:
        config = self.require_enabled()
        candidate = download.candidate
        if config.revision != candidate.revision:
            raise RemoteError("La configuration a changé ; relancer la recherche.")
        verify_download(download)
        # New UUID only: importing never associates or replaces a local choice.
        return self.imports.import_content(
            download.content,
            candidate.path.rsplit("/", 1)[-1],
            name=candidate.identifier,
            origin=AssetOrigin.KICAD_OFFICIAL,
            source_reference=candidate.source,
            symbol_name=candidate.name if candidate.asset_type is AssetType.SYMBOL else "",
        )
