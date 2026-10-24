"""Portable provenance and documented redistribution facts, independent of providers."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from kipartmanager.domain.entities import DomainError


class Redistribution(StrEnum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


def public_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port not in (None, 443)
            or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            raise ValueError
    except ValueError as error:
        raise DomainError(
            "Une URL publique HTTPS sans secret ni paramètres est requise."
        ) from error


@dataclass(frozen=True)
class AssetProvenance:
    provider: str
    provider_id: str
    source_url: str
    resolved_at: str
    imported_at: str
    sha256: str
    mpn: str
    manufacturer: str = ""
    package: str = ""
    license_name: str = ""
    license_url: str = ""
    attribution: str = ""
    redistribution: Redistribution = Redistribution.UNKNOWN
    rights_reference: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.redistribution, Redistribution):
            raise DomainError("État de redistribution invalide.")
        public_url(self.source_url)
        if self.license_url:
            public_url(self.license_url)
        for value in (self.provider, self.provider_id, self.mpn):
            if not value.strip():
                raise DomainError("Identité de provenance incomplète.")
        for value in (
            self.provider,
            self.provider_id,
            self.mpn,
            self.manufacturer,
            self.package,
            self.license_name,
            self.license_url,
            self.attribution,
            self.rights_reference,
        ):
            if len(value) > 4096 or "\x00" in value:
                raise DomainError("Champ de provenance invalide.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise DomainError("Hash de provenance invalide.")
        for value in (self.resolved_at, self.imported_at):
            try:
                if datetime.fromisoformat(value).tzinfo is None:
                    raise ValueError
            except ValueError as error:
                raise DomainError("Date de provenance invalide.") from error
        if self.redistribution is not Redistribution.UNKNOWN and not self.rights_reference.strip():
            raise DomainError("Un état de redistribution établi exige une référence de droits.")

    @property
    def summary(self) -> str:
        return (
            f"{self.provider} · {self.provider_id}\n{self.mpn} · {self.manufacturer or '—'}\n"
            f"Source : {self.source_url}\nImport : {self.imported_at}\n"
            f"Licence : {self.license_name or 'non communiquée'}\n{self.license_url}\n"
            f"Attribution : {self.attribution or 'non communiquée'}\n"
            f"Redistribution : {self.redistribution.value}\n"
            f"Référence de droits : {self.rights_reference or 'non établie'}"
        )
