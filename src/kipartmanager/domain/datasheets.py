"""Explicit manufacturer host authorization; no network implementation."""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from kipartmanager.domain.entities import DomainError


@dataclass(frozen=True)
class DatasheetConfiguration:
    enabled: bool = False
    domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or len(set(self.domains)) != len(self.domains):
            raise DomainError("Configuration de téléchargement invalide.")
        for domain in self.domains:
            if not re.fullmatch(
                r"(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+",
                domain,
            ):
                raise DomainError(
                    "Saisir des domaines DNS exacts en minuscules, sans URL ni joker."
                )
            if domain.rsplit(".", 1)[-1].isdigit() or domain.endswith(".localhost"):
                raise DomainError("Un domaine constructeur public est requis.")

    def authorize(self, url: str) -> None:
        if not self.enabled:
            raise DomainError(
                "Téléchargement constructeur désactivé ; la gestion locale reste disponible."
            )
        try:
            parsed = urlsplit(url)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname in self.domains
                and parsed.port in (None, 443)
                and not parsed.username
                and not parsed.password
                and not parsed.fragment
                and bool(parsed.path)
                and not any(c.isspace() or ord(c) < 32 for c in url)
            )
        except ValueError as error:
            raise DomainError("URL HTTPS constructeur invalide.") from error
        if not valid:
            raise DomainError(
                "URL HTTPS sur un domaine constructeur autorisé explicitement requise."
            )


@dataclass(frozen=True)
class DatasheetDownload:
    url: str
    content: bytes

    def __post_init__(self) -> None:
        if not 0 < len(self.content) <= 32 * 1024 * 1024 or b"%PDF-" not in self.content[:1024]:
            raise DomainError("Réponse sans signature PDF ou trop volumineuse ; aucun PDF importé.")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def filename(self) -> str:
        name = unquote(urlsplit(self.url).path.rsplit("/", 1)[-1])
        return (
            name
            if name.lower().endswith(".pdf") and not any(c in name for c in "/\\\x00")
            else "datasheet.pdf"
        )
