"""Explicit third-party lookup/import, preserving local priority and resource choices."""

from dataclasses import replace
from datetime import UTC, datetime

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Asset, AssetOrigin, DomainError
from kipartmanager.domain.third_party_assets import (
    AssetQuery,
    ProviderState,
    ThirdPartyCandidate,
    ThirdPartyConfiguration,
    ThirdPartyDownload,
    ThirdPartySearch,
)
from kipartmanager.ports.third_party_assets import (
    CandidateInspector,
    ThirdPartyProvider,
    ThirdPartySettings,
)


class ThirdPartyResolver:
    def __init__(
        self,
        catalogue: Catalogue,
        settings: ThirdPartySettings,
        inspector: CandidateInspector,
        provider: ThirdPartyProvider | None = None,
    ) -> None:
        self.catalogue, self.settings, self.inspector, self.provider = (
            catalogue,
            settings,
            inspector,
            provider,
        )

    def configuration(self) -> ThirdPartyConfiguration:
        return self.settings.load()

    def configure(self, config: ThirdPartyConfiguration) -> None:
        self.settings.save(config)

    def state(self) -> ProviderState:
        if not self.configuration().enabled:
            return ProviderState.DISABLED
        try:
            state = self.provider.state() if self.provider else ProviderState.NOT_CONFIGURED
            return state if isinstance(state, ProviderState) else ProviderState.NOT_CONFIGURED
        except Exception:
            return ProviderState.NOT_CONFIGURED

    def require_ready(self) -> None:
        state = self.state()
        messages = {
            ProviderState.DISABLED: "SnapMagic désactivé ; résolution locale disponible.",
            ProviderState.NOT_CONFIGURED: "SnapMagic non configuré : adaptateur ou secret absent.",
            ProviderState.CONTRACT_REQUIRED: (
                "Contrat API partenaire SnapMagic requis ; aucun endpoint non vérifié utilisé."
            ),
        }
        if state is not ProviderState.READY:
            raise DomainError(messages[state])

    def search(self, query: AssetQuery) -> ThirdPartySearch:
        self.require_ready()
        assert self.provider is not None
        result = self.provider.search(query)
        if not isinstance(result, ThirdPartySearch) or result.query != query:
            raise DomainError("Réponse du fournisseur invalide ; candidats non retenus.")
        if len(result.candidates) > 100 or any(
            not isinstance(c, ThirdPartyCandidate)
            or c.asset_type != query.asset_type
            or c.mpn.casefold() != query.mpn.casefold()
            or (query.manufacturer and c.manufacturer.casefold() != query.manufacturer.casefold())
            for c in result.candidates
        ):
            raise DomainError("Les candidats doivent correspondre au MPN exact et au type demandé.")
        return result

    def download(self, candidate: ThirdPartyCandidate) -> ThirdPartyDownload:
        self.require_ready()
        assert self.provider is not None
        result = self.provider.download(candidate)
        if not isinstance(result, ThirdPartyDownload) or result.candidate != candidate:
            raise DomainError("Téléchargement différent du candidat choisi.")
        self.inspector.inspect(result)
        return result

    def import_download(self, result: ThirdPartyDownload) -> Asset:
        self.require_ready()  # Revocation also applies after an in-flight download.
        self.inspector.inspect(result)
        if self.catalogue.store is None:
            raise DomainError("Asset Store indisponible.")
        candidate = result.candidate
        file = replace(
            self.catalogue.store.import_content(result.content, candidate.filename),
            symbol_name=candidate.symbol_name,
        )
        if file.sha256 != result.sha256 or file.asset_type != candidate.asset_type:
            raise DomainError("Identité du fichier importé incohérente.")
        asset = Asset(
            name=candidate.name,
            asset_type=candidate.asset_type,
            origin=AssetOrigin.TRUSTED_THIRD_PARTY,
            source=candidate.source_url,
            file=file,
            provenance=candidate.provenance(result.sha256, datetime.now(UTC).isoformat()),
        )
        self.catalogue.save(asset)
        return asset  # New UUID, no association, no selection and no qualification.
