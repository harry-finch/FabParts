"""SnapMagic boundary prepared for an authorized partner client, not a guessed API.

SnapMagic's public pages do not publish endpoints/authentication/response schemas.
PartnerClient is an INTERNAL normalized contract, never advertised as their wire API.
No default network client, browser login, scraping or fixture fallback is installed.
"""

import io
import os
import stat
import tempfile
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from kipartmanager.domain.asset_provenance import Redistribution
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.third_party_assets import (
    AssetQuery,
    ProviderState,
    ThirdPartyCandidate,
    ThirdPartyConfiguration,
    ThirdPartyDownload,
    ThirdPartySearch,
)
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe


class SnapMagicSettings:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "config" / "snapmagic.toml"

    def load(self) -> ThirdPartyConfiguration:
        try:
            if not self.path.exists():
                return ThirdPartyConfiguration()
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            return ThirdPartyConfiguration(data["enabled"])
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise DomainError(
                "Configuration SnapMagic illisible ; réenregistrer l’activation."
            ) from error

    def save(self, config: ThirdPartyConfiguration) -> None:
        staging: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as writer:
                staging = Path(writer.name)
                writer.write(f"enabled = {str(config.enabled).lower()}\n")
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(staging, self.path)
        except OSError as error:
            raise DomainError("Activation SnapMagic non enregistrée.") from error
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)


class CredentialReader(Protocol):
    def read(self) -> str | None: ...


class EnvironmentCredential:
    """Opaque partner credential, never logged or persisted; auth scheme is unresolved."""

    def read(self) -> str | None:
        value = os.environ.get("KIPART_SNAPMAGIC_CREDENTIAL", "")
        return value if value.strip() else None


@dataclass(frozen=True)
class SnapMagicRecord:
    """Internal normalization target for the FUTURE authorized client, not API JSON."""

    identity: str
    asset_type: AssetType
    name: str
    mpn: str
    manufacturer: str
    filename: str
    source_url: str
    package: str = ""
    symbol_name: str = ""
    sha256: str = ""
    license_name: str = ""
    license_url: str = ""
    attribution: str = ""
    redistribution: Redistribution = Redistribution.UNKNOWN
    rights_reference: str = ""


class PartnerClient(Protocol):
    """Implement only against partner documentation and an authorized API agreement.

    Bound response sizes, enforce HTTPS and credential destination, reject redirects,
    normalize the actual response to SnapMagicRecord, and never include secrets in
    public metadata. No endpoint or header convention is assumed by this port.
    """

    def search(self, query: AssetQuery, credential: str) -> tuple[SnapMagicRecord, ...]: ...
    def download(self, candidate: ThirdPartyCandidate, credential: str) -> bytes: ...


class SnapMagicRateLimit(Exception):
    """Normalized partner throttling; no invented quota or automatic retry."""

    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__()
        self.retry_after = retry_after if type(retry_after) is int and retry_after >= 0 else None


class SnapMagicAdapter:
    def __init__(self, credentials: CredentialReader, client: PartnerClient | None = None) -> None:
        self.credentials, self.client = credentials, client

    def state(self) -> ProviderState:
        if self.credentials.read() is None:
            return ProviderState.NOT_CONFIGURED
        return ProviderState.READY if self.client is not None else ProviderState.CONTRACT_REQUIRED

    def require_client(self) -> tuple[PartnerClient, str]:
        credential = self.credentials.read()
        if credential is None:
            raise DomainError("Identifiant API SnapMagic absent ; résolution locale disponible.")
        if self.client is None:
            raise DomainError("Contrat API partenaire SnapMagic requis avant tout accès réseau.")
        return self.client, credential

    @staticmethod
    def failure(error: Exception) -> DomainError:
        if isinstance(error, SnapMagicRateLimit):
            suffix = (
                f" Réessayer après {error.retry_after} s." if error.retry_after is not None else ""
            )
            return DomainError("Limite API SnapMagic atteinte ; aucun retry automatique." + suffix)
        if isinstance(error, (OSError, TimeoutError)):
            return DomainError(
                "SnapMagic inaccessible (réseau ou délai) ; ressources locales conservées."
            )
        # Client exceptions may contain tokens, signed URLs, headers or response bodies.
        return DomainError("Échec de l’adaptateur SnapMagic ; aucun détail confidentiel affiché.")

    def search(self, query: AssetQuery) -> ThirdPartySearch:
        client, credential = self.require_client()
        try:
            records = client.search(query, credential)
        except Exception as error:
            raise self.failure(error) from None
        try:
            if not isinstance(records, tuple) or len(records) > 100:
                raise ValueError
            candidates = []
            filtered = 0
            resolved_at = datetime.now(UTC).isoformat()
            for record in records:
                if not isinstance(record, SnapMagicRecord):
                    raise ValueError
                if any(
                    credential in value
                    for value in asdict(record).values()
                    if isinstance(value, str)
                ):
                    raise ValueError
                if (
                    record.mpn.casefold() != query.mpn.casefold()
                    or record.asset_type != query.asset_type
                    or (
                        query.manufacturer
                        and record.manufacturer.casefold() != query.manufacturer.casefold()
                    )
                ):
                    filtered += 1
                    continue
                candidates.append(
                    ThirdPartyCandidate(
                        "SnapMagic / SnapEDA",
                        record.identity,
                        record.asset_type,
                        record.name,
                        record.mpn,
                        record.manufacturer,
                        record.filename,
                        record.source_url,
                        resolved_at,
                        record.package,
                        record.symbol_name,
                        record.sha256,
                        record.license_name,
                        record.license_url,
                        record.attribution,
                        record.redistribution,
                        record.rights_reference,
                    )
                )
            if len({(c.provider_id, c.filename) for c in candidates}) != len(candidates):
                raise ValueError
            return ThirdPartySearch(
                query,
                tuple(candidates),
                (f"{filtered} résultat(s) hors MPN exact / fabricant / type écarté(s).",)
                if filtered
                else (),
            )
        except (ValueError, TypeError, AttributeError):
            raise DomainError(
                "Réponse SnapMagic invalide ou format non supporté ; aucun candidat retenu."
            ) from None

    def download(self, candidate: ThirdPartyCandidate) -> ThirdPartyDownload:
        if candidate.provider != "SnapMagic / SnapEDA":
            raise DomainError("Candidat d’un autre fournisseur.")
        client, credential = self.require_client()
        try:
            content = client.download(candidate, credential)
        except Exception as error:
            raise self.failure(error) from None
        if not isinstance(content, bytes) or not 0 < len(content) <= 32 * 1024 * 1024:
            raise DomainError("Téléchargement SnapMagic vide, invalide ou supérieur à 32 Mio.")
        if content.startswith(b"PK"):
            content = selected_zip_member(content, candidate.filename)
        return ThirdPartyDownload(candidate, content)


def selected_zip_member(content: bytes, filename: str) -> bytes:
    """Read exactly one named file in memory; never extract paths to disk."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 64 or sum(e.file_size for e in entries) > 64 * 1024 * 1024:
                raise ValueError
            for entry in entries:
                path = PurePosixPath(entry.filename)
                mode = entry.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in entry.filename
                    or ":" in entry.filename
                    or stat.S_ISLNK(mode)
                    or entry.flag_bits & 1
                    or entry.file_size > 32 * 1024 * 1024
                ):
                    raise ValueError
            matches = [
                e for e in entries if not e.is_dir() and PurePosixPath(e.filename).name == filename
            ]
            if len(matches) != 1:
                raise ValueError
            with archive.open(matches[0]) as reader:
                selected = reader.read(32 * 1024 * 1024 + 1)
            if len(selected) != matches[0].file_size:
                raise ValueError
            return selected
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
        raise DomainError(
            "Archive SnapMagic invalide, ambiguë ou non supportée ; aucun import."
        ) from None


class ThirdPartyInspector:
    def inspect(self, download: ThirdPartyDownload) -> None:
        candidate = download.candidate
        try:
            with tempfile.TemporaryDirectory(prefix="kipart-third-party-") as folder:
                source = Path(folder) / candidate.filename
                source.write_bytes(download.content)
                LocalResourceProbe._inspect(
                    source,
                    candidate.asset_type,
                    download.sha256,
                    candidate.symbol_name,
                    candidate.extension,
                )
        except (OSError, UnicodeError, DomainError):
            raise DomainError(
                "Format réel du candidat invalide ou non pris en charge ; aucun import."
            ) from None
