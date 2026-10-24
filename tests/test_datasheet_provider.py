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
