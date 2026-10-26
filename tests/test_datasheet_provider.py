"""Authorized manufacturer HTTP failures, response bounds and local settings recovery."""

from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from kipartmanager.domain.datasheets import DatasheetConfiguration
from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.datasheets import (
    ManufacturerPDFs,
    ManufacturerSettings,
    RejectRedirect,
)

URL = "https://docs.maker.example/r.pdf"
CONFIG = DatasheetConfiguration(True, ("docs.maker.example",))


class Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self, size: int) -> bytes:
        result, self.content = self.content[:size], self.content[size:]
        return result


def test_real_adapter_mocked_http_and_pdf_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Opener:
        def open(self, request: Request, *, timeout: int) -> Response:
            calls.append(request.full_url)
            assert timeout == 8
            return Response(b"%PDF-1.4\nbytes retained")

    monkeypatch.setattr(
        "kipartmanager.infrastructure.datasheets.build_opener", lambda *args: Opener()
    )
    provider = ManufacturerPDFs()
    with pytest.raises(DomainError, match="désactivé"):
        provider.download(URL, DatasheetConfiguration())
    with pytest.raises(DomainError, match="autorisé"):
        provider.download("https://other.example/file.pdf", CONFIG)
    assert calls == []
    result = provider.download(URL, CONFIG)
    assert calls == [URL] and result.filename == "r.pdf"
    assert result.content == b"%PDF-1.4\nbytes retained"


@pytest.mark.parametrize(
    "error",
    [
        URLError("offline"),
        TimeoutError(),
        HTTPError(URL, 404, "Missing", Message(), None),
        HTTPError(URL, 429, "Limited", Message(), None),
    ],
)
def test_http_failure_preserves_local_feature(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    class Opener:
        def open(self, *args: object, **kwargs: object) -> None:
            raise error

    monkeypatch.setattr(
        "kipartmanager.infrastructure.datasheets.build_opener", lambda *args: Opener()
    )
    with pytest.raises(DomainError, match="documents locaux conservés"):
        ManufacturerPDFs().download(URL, CONFIG)


@pytest.mark.parametrize(
    "content,expected",
    [(b"<html>login</html>", "signature"), (b"x" * (32 * 1024 * 1024 + 1), "volumineux")],
)
def test_non_pdf_and_excessive_response(
    monkeypatch: pytest.MonkeyPatch, content: bytes, expected: str
) -> None:
    class Opener:
        def open(self, *args: object, **kwargs: object) -> Response:
            return Response(content)

    monkeypatch.setattr(
        "kipartmanager.infrastructure.datasheets.build_opener", lambda *args: Opener()
    )
    with pytest.raises(DomainError, match=expected):
        ManufacturerPDFs().download(URL, CONFIG)


def test_redirect_requires_explicit_final_url() -> None:
    with pytest.raises(DomainError, match="Redirection"):
        RejectRedirect().redirect_request(
            Request(URL), None, 302, "Found", None, "https://other.example/r.pdf"
        )


def test_configuration_roundtrip_and_recovery(tmp_path: Path) -> None:
    settings = ManufacturerSettings(tmp_path)
    assert settings.load() == DatasheetConfiguration()
    settings.save(CONFIG)
    assert settings.load() == CONFIG
    settings.path.write_text('enabled = true\ndomains = "invalid"')
    with pytest.raises(DomainError, match="illlisible|illisible"):
        settings.load()
    settings.save(DatasheetConfiguration())
    assert settings.load() == DatasheetConfiguration()


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fec0::1",
        "4000::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",
    ],
)
def test_private_dns_answers_refused_before_connect(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    import socket

    from kipartmanager.infrastructure.datasheets import PublicHTTPSConnection

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))],
    )

    def refused(*args: object, **kwargs: object) -> None:
        pytest.fail("No socket may open for a private destination")

    monkeypatch.setattr(socket, "socket", refused)
    with pytest.raises(DomainError, match="non publique"):
        PublicHTTPSConnection("docs.maker.example", timeout=8).connect()


def test_dns_is_resolved_once_and_numeric_connection_keeps_tls_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import ssl

    from kipartmanager.infrastructure.datasheets import PublicHTTPSConnection

    resolved: list[str] = []
    connected: list[object] = []

    def resolve(host: str, port: int, **kwargs: object) -> list[object]:
        resolved.append(host)
        # A second resolution would be hostile. Only the first answer may be used.
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34" if len(resolved) == 1 else "127.0.0.1", 443),
            )
        ]

    class Socket:
        def settimeout(self, value: float) -> None:
            assert value == 8

        def connect(self, address: object) -> None:
            connected.append(address)

        def close(self) -> None:
            pass

    class TLS:
        def wrap_socket(self, value: object, *, server_hostname: str) -> object:
            assert server_hostname == "docs.maker.example"
            return value

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", lambda *a: Socket())
    monkeypatch.setattr(ssl, "create_default_context", lambda: TLS())
    connection = PublicHTTPSConnection("docs.maker.example", timeout=8)
    connection.connect()
    assert resolved == ["docs.maker.example"]
    assert connected == [("93.184.216.34", 443)]


def test_mixed_public_private_dns_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    from kipartmanager.infrastructure.datasheets import PublicHTTPSConnection

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.1.1.1", 443))],
    )
    with pytest.raises(DomainError, match="non publique"):
        PublicHTTPSConnection("docs.maker.example", timeout=8).connect()
