"""Optional AI suggestions: explicit consent, no authority to mutate local data."""

from kipartmanager.domain.assistance import AssistanceConfiguration, AssistanceRequest
from kipartmanager.domain.documentation import MetadataProposal
from kipartmanager.domain.entities import AssetOrigin, DomainError
from kipartmanager.ports.assistance import AssistanceProvider, AssistanceSettings


class Assistance:
    def __init__(
        self, settings: AssistanceSettings, provider: AssistanceProvider | None = None
    ) -> None:
        self.settings, self.provider = settings, provider

    def configuration(self) -> AssistanceConfiguration:
        return self.settings.load()

    def configure(self, config: AssistanceConfiguration) -> None:
        self.settings.save(config)

    def suggest(
        self,
        request: AssistanceRequest,
        expected_config: AssistanceConfiguration,
        *,
        consent: bool = False,
    ) -> MetadataProposal:
        if not consent:
            raise DomainError("Confirmer l’envoi du contexte affiché pour cette requête.")
        config = self.configuration()
        if config != expected_config:
            raise DomainError("Configuration modifiée ; relire la destination avant envoi.")
        if not config.enabled:
            raise DomainError("Assistance IA désactivée ; identification locale disponible.")
        try:
            if self.provider is None or not self.provider.available(config):
                raise DomainError(
                    "Fournisseur IA non configuré ; identification locale disponible."
                )
            result = self.provider.suggest(request, config)
        except DomainError:
            raise
        except Exception:
            raise DomainError("Fournisseur IA indisponible ; données locales conservées.") from None
        if (
            not isinstance(result, MetadataProposal)
            or result.source.origin is not AssetOrigin.GENERATED_AI
        ):
            raise DomainError("Proposition IA invalide ; aucun changement enregistré.")
        if self.configuration() != config:
            raise DomainError("Activation modifiée pendant la requête ; proposition écartée.")
        return result
