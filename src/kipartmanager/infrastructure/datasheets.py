"""Explicitly authorized manufacturer URLs, bounded PDFs and machine-local TOML."""

import json
import os
import tempfile
import time
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.entities import DomainError


class ManufacturerSettings:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "config" / "datasheets.toml"

    def load(self) -> DatasheetConfiguration:
        try:
            if not self.path.exists():
                return DatasheetConfiguration()
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data["domains"], list) or any(
                not isinstance(v, str) for v in data["domains"]
            ):
                raise ValueError("Invalid domains")
            return DatasheetConfiguration(data["enabled"], tuple(data["domains"]))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DomainError(
                "Configuration datasheets illisible ; réenregistrer l’autorisation."
            ) from error

    def save(self, config: DatasheetConfiguration) -> None:
        staging: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as writer:
                staging = Path(writer.name)
                writer.write(
                    f"enabled = {str(config.enabled).lower()}\n"
                    f"domains = {json.dumps(config.domains)}\n"
                )
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(staging, self.path)
        except OSError as error:
            raise DomainError("Autorisation constructeur non enregistrée.") from error
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        raise DomainError(
            "Redirection refusée ; autoriser puis saisir l’URL finale du constructeur."
        )


class ManufacturerPDFs:
    def download(self, url: str, config: DatasheetConfiguration) -> DatasheetDownload:
        config.authorize(url)
        try:
            request = Request(
                url, headers={"User-Agent": "KiPartManager-M10", "Accept-Encoding": "identity"}
            )
            with build_opener(RejectRedirect()).open(request, timeout=8) as response:
                limit = 32 * 1024 * 1024
                content = bytearray()
                deadline = time.monotonic() + 20
                while True:
                    chunk = response.read(min(65536, limit + 1 - len(content)))
                    content.extend(chunk)
                    if len(content) > limit:
                        raise DomainError("PDF constructeur trop volumineux (32 Mio maximum).")
                    if time.monotonic() > deadline:
                        raise DomainError(
                            "Délai de téléchargement dépassé ; documents locaux conservés."
                        )
                    if not chunk:
                        return DatasheetDownload(url, bytes(content))
        except HTTPError as error:
            raise DomainError(
                f"Téléchargement refusé (HTTP {error.code}) ; documents locaux conservés."
            ) from error
        except (URLError, OSError) as error:
            raise DomainError(
                "Constructeur inaccessible (réseau, TLS ou délai) ; documents locaux conservés."
            ) from error
