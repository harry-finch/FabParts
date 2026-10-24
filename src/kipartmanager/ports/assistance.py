"""Optional structured assistance, independent of catalogue writes."""

from typing import Protocol

from kipartmanager.domain.assistance import AssistanceConfiguration, AssistanceRequest
from kipartmanager.domain.documentation import MetadataProposal


class AssistanceSettings(Protocol):
    def load(self) -> AssistanceConfiguration: ...
    def save(self, config: AssistanceConfiguration) -> None: ...


class AssistanceProvider(Protocol):
    def available(self, config: AssistanceConfiguration) -> bool: ...
    def suggest(
        self, request: AssistanceRequest, config: AssistanceConfiguration
    ) -> MetadataProposal: ...
