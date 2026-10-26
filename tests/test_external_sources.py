"""Optional providers, preparation-bound capabilities and atomic canonical ingestion."""

import hashlib
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.external_sources import ExternalSources
from kipartmanager.application.ingestion import Ingestion
from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.domain.remote_kicad import (
    RemoteCandidate,
    RemoteDownload,
    RemoteSearch,
)
from kipartmanager.external_ipc import METHODS, validate
from kipartmanager.headless_ipc import respond
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import LocalProposalReader
from kipartmanager.infrastructure.remote_kicad import TomlRemoteSettings
from tests.test_ingestion import fields
from tests.test_ingestion import ingestion as ingestion
from tests.test_previews import FOOTPRINT, SYMBOL

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://docs.maker.example/device.pdf"


class Providers:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.changed = False
        self.bad_hash = False
        self.failure = False
        self.wait: threading.Event | None = None
        self.entered = threading.Event()
        self.content = {
            AssetType.SYMBOL: SYMBOL.encode(),
            AssetType.FOOTPRINT: FOOTPRINT.encode(),
            AssetType.MODEL_3D: (FIXTURES / "models/box.step").read_bytes(),
        }

    def search(self, revision: str, kind: AssetType, library: str, query: str) -> RemoteSearch:
        self.calls.append("search")
        self.entered.set()
        if self.wait:
            assert self.wait.wait(5)
        if self.failure:
            raise DomainError("offline")
        name = {
            AssetType.SYMBOL: "Child",
            AssetType.FOOTPRINT: "SOIC",
            AssetType.MODEL_3D: "box.step",
        }[kind]
        path = (
            library + ".kicad_sym"
            if kind is AssetType.SYMBOL
            else f"{library}.pretty/{name}.kicad_mod"
            if kind is AssetType.FOOTPRINT
            else f"{library}.3dshapes/{name}"
        )
        return RemoteSearch(
            (
                RemoteCandidate(
                    kind,
                    library,
                    name,
                    path,
                    revision,
                    "a" * 40,
                    sha256=hashlib.sha256(self.content[kind]).hexdigest(),
                    description="Fixture only",
                ),
            )
        )

    def download(self, candidate: RemoteCandidate) -> RemoteDownload:
        self.calls.append("download")
        self.entered.set()
        if self.wait:
            assert self.wait.wait(5)
        return RemoteDownload(
            replace(candidate, commit="b" * 40) if self.changed else candidate,
            b"changed" if self.bad_hash else self.content[candidate.asset_type],
        )


class PDFs:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.content = (FIXTURES / "previews/Synthetic.pdf").read_bytes()

    def download(self, url: str, config: DatasheetConfiguration) -> DatasheetDownload:
        config.authorize(url)
        self.calls.append(url)
        return DatasheetDownload(url, self.content)


def compose(service: Ingestion, root: Path) -> tuple[ExternalSources, Providers, PDFs]:
    provider, pdfs = Providers(), PDFs()
    return (
        ExternalSources(
            service,
            RemoteLibraries(
                TomlRemoteSettings(root), AssetImports(service.catalogue, service.store), provider
            ),
            Documentation(
                service.catalogue,
                service.documentation,
                LocalProposalReader(),
                ManufacturerSettings(root),
                pdfs,
            ),
        ),
        provider,
        pdfs,
    )


def complete(service: ExternalSources, preparation: str, job: dict[str, str]) -> dict[str, Any]:
    assert service.worker
    service.worker.join(5)
    assert not service.worker.is_alive()
    return service.status(preparation, job["handle"])


def search(service: ExternalSources, preparation: str, role: str = "SYMBOL") -> dict[str, Any]:
    job = service.search(preparation, role, "Timer", "Child")
    result = complete(service, preparation, job)
    assert result["status"] == "ready"
    return dict(result["candidates"][0])


def test_disabled_startup_configuration_and_offline_local(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, provider, pdfs = compose(ingestion, tmp_path)
    assert service.configuration() == {
        "kicad": {"enabled": False, "revision": "9.0.0"},
        "pdf": {"enabled": False, "domains": ()},
    }
    prep = ingestion.begin()["preparation"]
    with pytest.raises(DomainError, match="désactivée"):
        service.search(prep, "SYMBOL", "Timer", "Child")
    with pytest.raises(DomainError, match="désactivé"):
        service.pdf(prep, URL, True)
    assert provider.calls == pdfs.calls == []
    ingestion.discover(prep, fields(ingestion), "SYMBOL")
    assert provider.calls == []
    service.configure("kicad", True, "9.0.0", [])
    provider.failure = True
    assert (
        complete(service, prep, service.search(prep, "SYMBOL", "Timer", "Child"))["status"]
        == "error"
    )
    assert ingestion.search(prep, "FOOTPRINT")["candidates"] == []
    session = ingestion.preparation
    assert session
    assert (
        ingestion.commit(prep, str(session.operation_id), fields(ingestion), {})["status"]
        == "saved"
    )


def test_pinned_inherited_symbol_temporary_then_confirmed(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, provider, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    begin = ingestion.begin()
    prep = begin["preparation"]
    remote = search(service, prep)
    assert remote["revision"] == "9.0.0" and remote["commit"] == "a" * 40
    assert provider.calls == ["search"]
    assert not ingestion.catalogue.list_entities(Asset)
    job = service.download(prep, remote["token"])
    ready = complete(service, prep, job)
    assert ready["status"] == "ready"
    assert service.status(prep, job["handle"]) == ready  # Polling never imports twice.
    assert ready["file"]["symbols"] == ("Child",)
    token = ready["candidate"]["token"]
    assert ingestion.preview(prep, token)["status"] == "ready"
    assert not ingestion.catalogue.list_entities(Part)
    assert not ingestion.catalogue.list_entities(Asset)
    assert ingestion.search(prep, "SYMBOL")["candidates"][0]["origin"] == "KICAD_OFFICIAL"
    ingestion.commit(prep, begin["operation_id"], fields(ingestion), {"SYMBOL": token})
    asset = ingestion.catalogue.list_entities(Asset)[0]
    assert asset.origin is AssetOrigin.KICAD_OFFICIAL and asset.source == remote["source"]
    assert asset.file and asset.file.symbol_name == "Child"
    assert asset.file.sha256 == hashlib.sha256(SYMBOL.encode()).hexdigest()
    destination = tmp_path / "retained.kicad_sym"
    ingestion.store.retrieve(asset.file, str(destination))
    assert destination.read_bytes() == SYMBOL.encode()  # Complete parents preserved.


@pytest.mark.parametrize("role", ["FOOTPRINT", "MODEL_3D"])
def test_mechanical_download_and_explicit_import(
    ingestion: Ingestion, tmp_path: Path, role: str
) -> None:
    service, _, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    begin = ingestion.begin()
    prep = begin["preparation"]
    remote = search(service, prep, role)
    staged = complete(service, prep, service.download(prep, remote["token"]))
    assert staged["status"] == "ready"
    ingestion.commit(
        prep,
        begin["operation_id"],
        replace(fields(ingestion), package_name="External fixture"),
        {role: staged["candidate"]["token"]},
    )
    assert ingestion.catalogue.list_entities(Asset)[0].origin is AssetOrigin.KICAD_OFFICIAL


@pytest.mark.parametrize("mutation", ["changed", "bad_hash"])
def test_modified_candidate_or_hash_rejected_without_staging(
    ingestion: Ingestion, tmp_path: Path, mutation: str
) -> None:
    service, provider, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    prep = ingestion.begin()["preparation"]
    candidate = search(service, prep)
    setattr(provider, mutation, True)
    assert complete(service, prep, service.download(prep, candidate["token"]))["status"] == "error"
    assert ingestion.files.files(prep) == ()
    assert not ingestion.catalogue.list_entities(Asset)


def test_configuration_change_revokes_candidates_and_inflight_result(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, provider, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    prep = ingestion.begin()["preparation"]
    candidate = search(service, prep)
    service.configure("kicad", True, "10.0.0", [])
    with pytest.raises(DomainError):
        service.download(prep, candidate["token"])
    job = service.search(prep, "SYMBOL", "Timer", "Child")
    service.configure("kicad", False, "10.0.0", [])
    assert service.worker
    service.worker.join(5)
    with pytest.raises(DomainError):
        service.status(prep, job["handle"])
    assert ingestion.files.files(prep) == ()


@pytest.mark.parametrize("phase", ["search", "download"])
def test_cancel_running_job_is_bounded_and_never_stages(
    ingestion: Ingestion, tmp_path: Path, phase: str
) -> None:
    service, provider, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    prep = ingestion.begin()["preparation"]
    candidate = search(service, prep) if phase == "download" else None
    provider.wait = threading.Event()
    provider.entered.clear()
    job = (
        service.download(prep, candidate["token"])
        if candidate
        else service.search(prep, "SYMBOL", "Timer", "Child")
    )
    assert provider.entered.wait(2)
    assert service.status(prep, job["handle"])["status"] == "loading"
    service.cancel(prep, job["handle"])
    with pytest.raises(DomainError, match="encore en cours"):
        service.search(prep, "SYMBOL", "Timer", "Child")
    assert (
        ingestion.search(prep, "SYMBOL")["candidates"] == []
    )  # Navigation/local work remains possible.
    provider.wait.set()
    assert service.worker
    service.worker.join(5)
    with pytest.raises(DomainError):
        service.status(prep, job["handle"])
    assert ingestion.files.files(prep) == ()
    assert not ingestion.catalogue.list_entities(Part)


def test_pdf_consent_preview_cancel_and_confirmed_provenance(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, _, provider = compose(ingestion, tmp_path)
    service.configure("pdf", True, "9.0.0", ["docs.maker.example"])
    begin = ingestion.begin()
    prep = begin["preparation"]
    with pytest.raises(DomainError):
        service.pdf(prep, URL, False)
    with pytest.raises(DomainError):
        service.pdf(prep, "https://other.example/f.pdf", True)
    assert not provider.calls
    ready = complete(service, prep, service.pdf(prep, URL, True))
    assert ready["status"] == "ready"
    assert not ingestion.catalogue.list_entities(Asset)
    ingestion.cancel(prep)
    assert not ingestion.catalogue.list_entities(Part)
    with pytest.raises(DomainError):
        service.status(prep, service.job.handle if service.job else "")
    begin = ingestion.begin()
    prep = begin["preparation"]
    ready = complete(service, prep, service.pdf(prep, URL, True))
    ingestion.commit(
        prep, begin["operation_id"], fields(ingestion), {"DATASHEET": ready["candidate"]["token"]}
    )
    asset = ingestion.catalogue.list_entities(Asset)[0]
    assert asset.origin is AssetOrigin.MANUFACTURER and asset.source == URL
    assert asset.file and asset.file.sha256 == hashlib.sha256(provider.content).hexdigest()


@pytest.mark.parametrize(
    "bad", [b"%PDF-1.4\ntruncated", b"%PDF-" + b"x" * (16 * 1024 * 1024) + b"%%EOF"]
)
def test_bad_or_over_staging_limit_pdf_leaves_no_transfer(
    ingestion: Ingestion, tmp_path: Path, bad: bytes
) -> None:
    service, _, provider = compose(ingestion, tmp_path)
    service.configure("pdf", True, "9.0.0", ["docs.maker.example"])
    provider.content = bad
    prep = ingestion.begin()["preparation"]
    result = complete(service, prep, service.pdf(prep, URL, True))
    assert result["status"] == "error"
    assert ingestion.files.files(prep) == ()
    assert not ingestion.catalogue.list_entities(Asset)
    assert isinstance(ingestion.files.root, Path)  # type: ignore[attr-defined]
    assert list((ingestion.files.root / prep).iterdir()) == []  # type: ignore[attr-defined]


def test_cross_preparation_and_unconfirmed_interruption(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, _, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    prep = ingestion.begin()["preparation"]
    candidate = search(service, prep)
    ready = complete(service, prep, service.download(prep, candidate["token"]))
    other = ingestion.begin()["preparation"]
    with pytest.raises(DomainError):
        service.download(other, candidate["token"])
    with pytest.raises(DomainError):
        ingestion.preview(other, ready["candidate"]["token"])
    assert not ingestion.catalogue.list_entities(Asset)
    assert not ingestion.catalogue.list_entities(Part)


def test_external_ipc_readonly_and_strict_shapes(ingestion: Ingestion, tmp_path: Path) -> None:
    service, _, _ = compose(ingestion, tmp_path)
    for method in METHODS:
        response = respond(
            json.dumps(
                {"protocol_version": 1, "request_id": "test", "method": method, "params": {}}
            ).encode(),
            ingestion.previews.catalogue,
            external=service,
        )
        assert response["error"]["code"] == "READ_ONLY"
    for raw in [
        {"preparation": "a" * 48, "token": "b" * 48, "candidate": {}},
        {"preparation": "a" * 48, "token": "../path"},
    ]:
        with pytest.raises(ValueError):
            validate("external_download", raw)
    with pytest.raises(ValueError):
        validate("external_pdf", {"preparation": "a" * 48, "url": URL, "consent": "true"})
    with pytest.raises(ValueError):
        validate(
            "external_configure",
            {"source": "pdf", "enabled": True, "revision": "9.0.0", "domains": ["a.example"] * 33},
        )


def test_remote_32_mib_transport_does_not_expand_16_mib_preparation(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    service, provider, _ = compose(ingestion, tmp_path)
    service.configure("kicad", True, "9.0.0", [])
    provider.content[AssetType.MODEL_3D] = (
        b"ISO-10303-21;" + b" " * (16 * 1024 * 1024) + b"END-ISO-10303-21;"
    )
    prep = ingestion.begin()["preparation"]
    candidate = search(service, prep, "MODEL_3D")
    result = complete(service, prep, service.download(prep, candidate["token"]))
    assert result["status"] == "error" and "16 Mio" in result["message"]
    assert not ingestion.files.files(prep)
    assert not ingestion.catalogue.list_entities(Asset)
