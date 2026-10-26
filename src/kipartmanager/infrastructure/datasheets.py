"""Explicitly authorized manufacturer URLs, bounded PDFs and machine-local TOML."""

import http.client
import ipaddress
import json
import os
import socket
import ssl
import tempfile
import time
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

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


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Resolve once, reject non-public answers, connect to a checked numeric address.

    TLS still verifies the original DNS name. No proxy or second host resolution
    can redirect this request to an internal service (including DNS rebinding).
    """

    def connect(self) -> None:
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise DomainError("Constructeur sans adresse publique.")
        for _, _, _, _, address in addresses:
            ip = ipaddress.ip_address(address[0])
            if (
                not ip.is_global
                or ip.is_multicast
                or ip.is_reserved
                or isinstance(ip, ipaddress.IPv6Address)
                and (
                    ip.is_site_local
                    or ip.ipv4_mapped is not None
                    or ip.sixtofour is not None
                    or ip.teredo is not None
                )
            ):
                raise DomainError("Destination réseau privée ou non publique refusée.")
        family, socktype, proto, _, address = addresses[0]
        connection = socket.socket(family, socktype, proto)
        try:
            connection.settimeout(self.timeout)
            connection.connect(address)  # Numeric sockaddr from the validated resolution.
            self.sock = ssl.create_default_context().wrap_socket(
                connection, server_hostname=self.host
            )
        except BaseException:
            connection.close()
            raise


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, req: Request) -> http.client.HTTPResponse:
        return self.do_open(PublicHTTPSConnection, req)


class ManufacturerPDFs:
    def download(self, url: str, config: DatasheetConfiguration) -> DatasheetDownload:
        config.authorize(url)
        try:
            request = Request(
                url, headers={"User-Agent": "KiPartManager-M10", "Accept-Encoding": "identity"}
            )
            with build_opener(ProxyHandler({}), PublicHTTPSHandler(), RejectRedirect()).open(
                request, timeout=8
            ) as response:
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
