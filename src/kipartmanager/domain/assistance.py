"""Bounded, explicitly shared identification context; no provider implementation."""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote, urlsplit
from uuid import UUID

from kipartmanager.domain.documentation import FieldValue
from kipartmanager.domain.entities import DomainError


class AssistanceBackend(StrEnum):
    GEMINI = "gemini"
    CHAT = "chat"
    OLLAMA = "ollama"


@dataclass(frozen=True)
class AssistanceConfiguration:
    enabled: bool = False
    endpoint: str = ""
    model: str = ""
    backend: AssistanceBackend = AssistanceBackend.CHAT

    def __post_init__(self) -> None:
        if not isinstance(self.backend, AssistanceBackend):
            raise DomainError("Type de fournisseur IA invalide.")
        if type(self.enabled) is not bool:
            raise DomainError("Activation IA invalide.")
        if self.endpoint:
            try:
                url = urlsplit(self.endpoint)
                local = self.backend is AssistanceBackend.OLLAMA
                gemini = self.backend is AssistanceBackend.GEMINI
                if (
                    (
                        local
                        and (
                            url.scheme != "http"
                            or url.hostname != "127.0.0.1"
                            or url.path != "/api/chat"
                        )
                    )
                    or (
                        not local
                        and not gemini
                        and (url.scheme != "https" or not url.path.endswith("/chat/completions"))
                    )
                    or (
                        gemini
                        and self.endpoint != "https://generativelanguage.googleapis.com/v1beta"
                    )
                    or not url.hostname
                    or url.username is not None
                    or url.password is not None
                    or url.query
                    or url.fragment
                    or (not local and url.port not in (None, 443))
                    or len(self.endpoint) > 512
                    or any(c.isspace() or ord(c) < 32 for c in self.endpoint)
                ):
                    raise ValueError
            except ValueError:
                raise DomainError(
                    "URL finale HTTPS /chat/completions ou Ollama "
                    "http://127.0.0.1:port/api/chat requise."
                ) from None
        if self.model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", self.model):
            raise DomainError("Nom de modèle invalide.")
        if self.enabled and (not self.endpoint or not self.model):
            raise DomainError("Renseigner URL et modèle avant activation.")

    @property
    def destination(self) -> str:
        if self.backend is AssistanceBackend.GEMINI:
            return f"{self.endpoint}/models/{quote(self.model, safe='')}:generateContent"
        return self.endpoint


@dataclass(frozen=True)
class AssistanceRequest:
    part_id: UUID
    revision: int
    text: str
    values: tuple[FieldValue, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip() or len(self.text) > 16000 or "\x00" in self.text:
            raise DomainError("Saisir un contexte de 1 à 16 000 caractères.")
        if len(self.values) > 4 or len({v.field for v in self.values}) != len(self.values):
            raise DomainError("Contexte d’identification invalide.")
        if type(self.revision) is not int or self.revision < 0:
            raise DomainError("Révision du contexte invalide.")

    @property
    def payload(self) -> str:
        # UUID, revision, paths, assets, history and inventories are NEVER sent.
        return json.dumps(
            {"context": self.text, "identification": {v.field.value: v.value for v in self.values}},
            ensure_ascii=False,
            sort_keys=True,
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload.encode()).hexdigest()
