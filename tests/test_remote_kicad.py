"""Deterministic official HTTP fixtures, opt-in isolation and preserved local choices."""

import hashlib
import json
from dataclasses import replace
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import Engine

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.domain.remote_kicad import (
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteError,
    verify_download,
)
from kipartmanager.domain.resolution import CandidateTier
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.remote_kicad import OfficialGitLab, TomlRemoteSettings, fetch

COMMIT = "a" * 40
SYMBOL = (
    b'(kicad_symbol_lib (version 20241209) (generator fixture) (symbol "R") '
    b'(symbol "R_Small" (extends "R") (property "Description" "Small resistor")))'
)
FOOTPRINT = b'(footprint "R_0603" (version 20241229) (generator fixture))'
MODEL = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"


def git_blob(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


class FixtureHTTP:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failure = ""
        self.content = SYMBOL

    def __call__(self, url: str, limit: int) -> bytes:
        self.calls.append(url)
        assert url.startswith("https://gitlab.com/api/v4/projects/kicad%2Flibraries%2F")
        if self.failure:
            raise RemoteError(self.failure)
        parts = urlparse(url)
        params = parse_qs(parts.query)
        if "/commits/" in url:
            return json.dumps({"id": COMMIT}).encode()
        assert params["ref"] == [COMMIT]
        if "/tree?" in url:
            path = params["path"][0]
            filename, content = (
                ("R_0603.kicad_mod", FOOTPRINT)
                if path.endswith(".pretty")
                else ("R_0603.step", MODEL)
            )
            return json.dumps(
                [
                    {
                        "name": filename,
                        "path": f"{path}/{filename}",
                        "id": git_blob(content),
                        "type": "blob",
                    }
                ]
            ).encode()
        if "kicad-symbols" in url:
            return self.content
        return FOOTPRINT if "kicad-footprints" in url else MODEL


@pytest.fixture
def remote_setup(
    engine: Engine, tmp_path: Path
) -> tuple[RemoteLibraries, LocalResolver, FixtureHTTP]:
    repository = SqliteCatalogue(engine)
    store = LocalAssetStore(tmp_path / "assets")
    imports = AssetImports(Catalogue(repository, store), store)
    http = FixtureHTTP()
    remote = RemoteLibraries(TomlRemoteSettings(tmp_path), imports, OfficialGitLab(http))
    return remote, LocalResolver(imports.catalogue, repository), http


@pytest.mark.parametrize(
    "kind,library,query",
    [
        (AssetType.SYMBOL, "Device", "Small resistor"),
        (AssetType.FOOTPRINT, "Resistor_SMD", "R_0603"),
        (AssetType.MODEL_3D, "Resistor_SMD", "R_0603"),
    ],
)
def test_official_pinned_download(
    remote_setup: tuple[RemoteLibraries, LocalResolver, FixtureHTTP],
    kind: AssetType,
    library: str,
    query: str,
) -> None:
    remote, local, http = remote_setup
    remote.configure(RemoteConfiguration(True, "9.0.0"))
    result = remote.search(kind, library, query)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.commit == COMMIT and candidate.revision == "9.0.0"
    assert local.catalogue.list_entities(Asset) == []
    asset = remote.import_download(remote.download(candidate))
    assert asset.file is not None
    assert (
        asset.file.sha256
        == hashlib.sha256(
            {AssetType.SYMBOL: SYMBOL, AssetType.FOOTPRINT: FOOTPRINT, AssetType.MODEL_3D: MODEL}[
                kind
            ]
        ).hexdigest()
    )
    assert asset.origin is AssetOrigin.KICAD_OFFICIAL
    assert COMMIT in asset.source and "ref=9.0.0" in asset.source
    assert asset.file.symbol_name == ("R_Small" if kind is AssetType.SYMBOL else "")
    assert asset.validation_state == "UNCHECKED"
    assert http.calls


def test_remote_never_replaces_and_remains_usable_offline(
    remote_setup: tuple[RemoteLibraries, LocalResolver, FixtureHTTP],
) -> None:
    remote, local, http = remote_setup
    user = remote.imports.import_content(
        SYMBOL,
        "user.kicad_sym",
        name="R_Small",
        origin=AssetOrigin.USER_PROVIDED,
        source_reference="user",
    )
    part = Part(name="R_Small", asset_ids=(user.id,))
    local.catalogue.save(part)
    candidate = local.search(part, AssetType.SYMBOL, "R_Small").candidates[0]
    local.select(part, candidate)
    remote.configure(RemoteConfiguration(True))
    distant = remote.search(AssetType.SYMBOL, "Device", "R_Small").candidates[0]
    asset = remote.import_download(remote.download(distant))
    assert local.choices(part) == (candidate.choice,)
    assert local.catalogue.require(Asset, user.id) == user
    assert local.catalogue.require(Part, part.id).asset_ids == (user.id,)
    http.failure = "Réseau indisponible"
    with pytest.raises(RemoteError, match="Réseau"):
        remote.search(AssetType.SYMBOL, "Device", "R")
    result = local.search(part, AssetType.SYMBOL, "R_Small")
    assert [c.tier for c in result.candidates] == [CandidateTier.USER, CandidateTier.REMOTE]
    imported = next(c for c in result.candidates if c.asset and c.asset.id == asset.id)
    with pytest.raises(DomainError, match="Confirmer"):
        local.select(part, imported, expected=candidate.choice)
    remote.configure(RemoteConfiguration(False))
    local.select(part, imported, expected=candidate.choice, replace_existing=True)
    assert local.choices(part) == (imported.choice,)
    assert local.catalogue.require(Asset, user.id) == user
    # Reimport is a distinct candidate, not an overwrite (store content deduplicates).
    assert asset.file is not None
    local.catalogue.store.verify(asset.file) if local.catalogue.store else None


def test_disabled_absent_and_bad_config_do_not_call_network(
    remote_setup: tuple[RemoteLibraries, LocalResolver, FixtureHTTP],
    tmp_path: Path,
) -> None:
    remote, _, http = remote_setup
    assert remote.configuration() == RemoteConfiguration()
    with pytest.raises(RemoteError, match="désactivée"):
        remote.search(AssetType.SYMBOL, "Device", "R")
    assert http.calls == []
    remote.configure(RemoteConfiguration(True))
    remote.provider = None
    with pytest.raises(RemoteError, match="absent"):
        remote.search(AssetType.SYMBOL, "Device", "R")
    assert http.calls == []
    (tmp_path / "config/remote-kicad.toml").write_text('enabled = "yes"\nrevision = "bad/ref"')
    with pytest.raises(RemoteError):
        remote.configuration()
    remote.configure(RemoteConfiguration(False, "8.0.0"))
    assert remote.configuration() == RemoteConfiguration(False, "8.0.0")


def test_stale_configuration_and_corruption_block_import(
    remote_setup: tuple[RemoteLibraries, LocalResolver, FixtureHTTP],
) -> None:
    remote, local, http = remote_setup
    remote.configure(RemoteConfiguration(True))
    candidate = remote.search(AssetType.SYMBOL, "Device", "R_Small").candidates[0]
    http.content = SYMBOL + b" "
    with pytest.raises(RemoteError, match="SHA-256"):
        remote.download(candidate)
    with pytest.raises(RemoteError):
        remote.import_download(RemoteDownload(candidate, b"altered"))
    remote.configure(RemoteConfiguration(True, "8.0.0"))
    with pytest.raises(RemoteError, match="changé"):
        remote.download(candidate)
    assert local.catalogue.list_entities(Asset) == []


@pytest.mark.parametrize("path", ["../Device.kicad_sym", "/Device.kicad_sym", "other.kicad_sym"])
def test_invalid_paths(path: str) -> None:
    with pytest.raises(RemoteError):
        RemoteCandidate(AssetType.SYMBOL, "Device", "R", path, "9.0.0", COMMIT, sha256="b" * 64)


def test_bad_payloads_and_git_integrity() -> None:
    with pytest.raises(RemoteError, match="JSON"):
        OfficialGitLab(lambda url, limit: b"html error").search(
            "9.0.0", AssetType.SYMBOL, "Device", "R"
        )
    with pytest.raises(RemoteError):
        OfficialGitLab(lambda url, limit: b"{}").search("9.0.0", AssetType.SYMBOL, "Device", "R")
    candidate = RemoteCandidate(
        AssetType.FOOTPRINT,
        "Resistor_SMD",
        "R_0603",
        "Resistor_SMD.pretty/R_0603.kicad_mod",
        "9.0.0",
        COMMIT,
        blob=git_blob(FOOTPRINT),
    )
    with pytest.raises(RemoteError, match="blob Git"):
        verify_download(RemoteDownload(candidate, FOOTPRINT + b" "))
    with pytest.raises(RemoteError, match="LFS"):
        verify_download(RemoteDownload(candidate, b"version https://git-lfs.github.com/spec/v1\n"))
    with pytest.raises(RemoteError, match="vide"):
        verify_download(RemoteDownload(candidate, b""))
    wrong = replace(candidate, name="wrong", path="Resistor_SMD.pretty/wrong.kicad_mod")
    with pytest.raises(RemoteError, match="Nom du footprint"):
        OfficialGitLab(lambda url, limit: FOOTPRINT).download(wrong)


@pytest.mark.parametrize(
    "error,expected",
    [
        (URLError("offline"), "inaccessible"),
        (HTTPError("https://gitlab.com", 404, "Missing", Message(), None), "introuvable"),
        (HTTPError("https://gitlab.com", 429, "Limited", Message(), None), "Limite"),
    ],
)
def test_http_errors(monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str) -> None:
    class Broken:
        def open(self, *args: object, **kwargs: object) -> None:
            raise error

    monkeypatch.setattr(
        "kipartmanager.infrastructure.remote_kicad.build_opener", lambda *args: Broken()
    )
    with pytest.raises(RemoteError, match=expected):
        fetch("https://gitlab.com/fixture", 100)


def test_limits_pagination_and_malformed_symbols() -> None:
    calls: list[int] = []

    def pages(url: str, limit: int) -> bytes:
        if "/commits/" in url:
            return json.dumps({"id": COMMIT}).encode()
        page = int(parse_qs(urlparse(url).query)["page"][0])
        calls.append(page)
        items = [
            {
                "name": f"R_{i}.kicad_mod",
                "path": f"Resistor_SMD.pretty/R_{i}.kicad_mod",
                "id": "b" * 40,
                "type": "blob",
            }
            for i in range((page - 1) * 100, page * 100)
        ]
        return json.dumps(items).encode()

    result = OfficialGitLab(pages).search("9.0.0", AssetType.FOOTPRINT, "Resistor_SMD", "")
    assert calls == list(range(1, 21))
    assert len(result.candidates) == 200
    assert len(result.notices) == 2
    http = FixtureHTTP()
    http.content = SYMBOL[:-1]
    with pytest.raises(DomainError, match="terminée"):
        OfficialGitLab(http).search("9.0.0", AssetType.SYMBOL, "Device", "")


def test_http_body_limit_and_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    from kipartmanager.infrastructure.remote_kicad import NoRedirect

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, size: int) -> bytes:
            return b"x" * size

    class Opener:
        def open(self, *args: object, **kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(
        "kipartmanager.infrastructure.remote_kicad.build_opener", lambda *args: Opener()
    )
    with pytest.raises(RemoteError, match="volumineuse"):
        fetch("https://gitlab.com/fixture", 10)
    from urllib.request import Request

    with pytest.raises(RemoteError, match="Redirection"):
        NoRedirect().redirect_request(
            Request("https://gitlab.com"), None, 302, "Found", None, "https://example.org"
        )


def test_imported_remote_symbol_publishes_and_transfers_offline(
    tmp_path: Path,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.infrastructure.bundles import LocalBundles
    from kipartmanager.infrastructure.database import create_database_engine, migrate
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications
    from tests.test_validation import SYMBOL as VALID_SYMBOL
    from tests.test_validation import setup_case

    validation, resolver, part, _, collection, _ = setup_case(tmp_path, engine)
    assert isinstance(validation.catalogue.store, LocalAssetStore)
    imports = AssetImports(validation.catalogue, validation.catalogue.store)
    http = FixtureHTTP()
    http.content = VALID_SYMBOL.encode().replace(
        b'(symbol "R" (symbol', b'(symbol "R_Small" (extends "R")) (symbol "R" (symbol', 1
    )
    remote = RemoteLibraries(TomlRemoteSettings(tmp_path), imports, OfficialGitLab(http))
    remote.configure(RemoteConfiguration(True))
    candidate = remote.search(AssetType.SYMBOL, "Device", "R_Small").candidates[0]
    asset = remote.import_download(remote.download(candidate))
    result = resolver.search(part, AssetType.SYMBOL, "R_Small")
    selected = next(c for c in result.candidates if c.asset and c.asset.id == asset.id)
    resolver.select(part, selected, expected=resolver.choices(part)[0], replace_existing=True)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    http.failure = "offline"
    validation.validate(collection)
    validation.require_publishable(collection)
    root = tmp_path / "history"
    builder = LocalLibraryBuilder(validation.catalogue.store, LocalKiCadIndex(root), root)
    history = LocalPublications(root / "publications", builder)
    service = Publications(LocalPublisher(validation.catalogue, validation, builder), history)
    publication = service.publish(collection, 1)
    history.verify(publication)
    assert isinstance(validation.catalogue.repository, SqliteCatalogue)
    archive = tmp_path / "remote.kiparts"
    LocalBundles(validation.catalogue.repository, history).export(publication, str(archive))
    target_root = tmp_path / "target"
    target_engine = create_database_engine(target_root / "database.sqlite3")
    try:
        migrate(target_engine)
        store = LocalAssetStore(target_root / "assets")
        target_history = LocalPublications(
            target_root / "publications",
            LocalLibraryBuilder(store, LocalKiCadIndex(target_root), target_root),
        )
        target = LocalBundles(SqliteCatalogue(target_engine), target_history)
        target.import_bundle(str(archive))
        transferred = Catalogue(target.repository, store).require(Asset, asset.id)
        assert transferred.file == asset.file and transferred.source == asset.source
        target_history.verify(publication)
        target_history.rebuild(publication, str(tmp_path / "rebuilt"))
    finally:
        target_engine.dispose()


def test_remote_import_keeps_all_local_tiers_first(
    remote_setup: tuple[RemoteLibraries, LocalResolver, FixtureHTTP],
    tmp_path: Path,
) -> None:
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.domain.kicad import LibraryRoots
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex

    remote, local, _ = remote_setup
    for origin in (AssetOrigin.USER_PROVIDED, AssetOrigin.MANAGED_LIBRARY):
        remote.imports.import_content(
            SYMBOL, "R.kicad_sym", name="R_Small", origin=origin, source_reference="local"
        )
    official = tmp_path / "official"
    official.mkdir()
    file = official / "Device.kicad_sym"
    file.write_bytes(SYMBOL)
    index = LocalKiCadIndex(tmp_path)
    index.configure(LibraryRoots(symbols=str(official)))
    index.rebuild(index.configuration())
    local.libraries = KiCadLibraries(index)
    part = Part(name="R_Small")
    local.catalogue.save(part)
    remote.configure(RemoteConfiguration(True))
    candidate = remote.search(AssetType.SYMBOL, "Device", "R_Small").candidates[0]
    remote.import_download(remote.download(candidate))
    assert [c.tier for c in local.search(part, AssetType.SYMBOL, "R_Small").candidates] == [
        CandidateTier.USER,
        CandidateTier.MANAGED,
        CandidateTier.KICAD,
        CandidateTier.REMOTE,
    ]
    assert local.choices(part) == ()
    assert file.read_bytes() == SYMBOL
