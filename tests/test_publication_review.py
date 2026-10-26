"""The Tauri bridge delegates all publication semantics to M5/M6/M7."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.publication_review import PublicationReview
from kipartmanager.application.publications import Publications
from kipartmanager.domain.entities import Collection, DomainError, Part
from kipartmanager.headless_ipc import respond
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.publication_ipc import validate
from tests.test_publications import folder
from tests.test_publications import publications as publication_fixture
from tests.test_publisher import tree_files

publications = publication_fixture


def test_summary_confirmation_and_durable_lost_reply(
    publications: tuple[Publications, Collection],
) -> None:
    service, collection = publications
    bridge = PublicationReview(service)
    identity = str(collection.id)
    assert bridge.history(identity)["proposed"] == 1
    preview = bridge.prepare(identity)
    assert preview["count"] == 1 and len(preview["parts"][0]["resources"]) == 2
    bridge.publish(identity, 1, preview["handle"])
    # Simulate a response lost after COMMIT, then a new engine session.
    restarted = PublicationReview(service)
    assert restarted.status(identity, 1)["status"] == "COMMITTED"
    assert restarted.status(identity, 1)["fingerprint"] == preview["fingerprint"]
    assert restarted.history(identity)["proposed"] == 2
    assert restarted.history(identity)["versions"][0]["verification"] == "NOT_CHECKED"
    assert restarted.verify(identity, 1)["verification"] == "PASS"
    with pytest.raises(DomainError):
        restarted.publish(identity, 1, preview["handle"])
    assert len(service.list_publications()) == 1


def test_reserved_number_is_skipped_and_never_valid(
    publications: tuple[Publications, Collection],
) -> None:
    service, collection = publications
    bridge = PublicationReview(service)
    folder(service, collection, 7).mkdir(parents=True)
    identity = str(collection.id)
    assert bridge.history(identity)["proposed"] == 8
    assert bridge.history(identity)["reserved_count"] == 1
    assert bridge.status(identity, 7)["status"] == "RESERVED"
    assert bridge.status(identity, 6)["status"] == "ABSENT"
    with pytest.raises(DomainError):
        bridge.verify(identity, 7)
    with pytest.raises(DomainError):
        service.publish(collection, 7)


def test_changed_summary_cannot_be_confirmed(publications: tuple[Publications, Collection]) -> None:
    service, collection = publications
    bridge = PublicationReview(service)
    preview = bridge.prepare(str(collection.id))
    part = service.publisher.catalogue.require(Part, collection.part_ids[0])
    service.publisher.catalogue.save(replace(part, name="Changed"))
    service.publisher.validation.validate(collection)
    with pytest.raises(DomainError):
        bridge.publish(str(collection.id), 1, preview["handle"])
    assert service.list_publications() == ()


@pytest.mark.parametrize("state", ["absent", "stale", "error", "warning"])
def test_collection_qualification_is_required(
    publications: tuple[Publications, Collection], state: str
) -> None:
    service, collection = publications
    validation = service.publisher.validation
    if state == "absent":
        collection = Collection(name="Without report", part_ids=collection.part_ids)
        validation.catalogue.save(collection)
        validation.validate(validation.catalogue.require(Part, collection.part_ids[0]))
    elif state == "stale":
        validation.catalogue.save(replace(collection, name="Stale"))
    elif state == "error":
        validation.catalogue.save(replace(collection, part_ids=()))
        validation.validate(collection)
    else:
        from kipartmanager.domain.entities import Asset, AssetOrigin

        asset = validation.catalogue.list_entities(Asset)[0]
        validation.catalogue.save(replace(asset, origin=AssetOrigin.GENERATED_PARAMETRIC))
        validation.validate(collection)
    with pytest.raises(DomainError):
        PublicationReview(service).prepare(str(collection.id))


def test_accepted_warning_delegated_to_m7(publications: tuple[Publications, Collection]) -> None:
    from kipartmanager.domain.entities import Asset, AssetOrigin

    service, collection = publications
    validation = service.publisher.validation
    asset = validation.catalogue.list_entities(Asset)[0]
    validation.catalogue.save(replace(asset, origin=AssetOrigin.GENERATED_PARAMETRIC))
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    bridge = PublicationReview(service)
    preview = bridge.prepare(str(collection.id))
    assert preview["warnings"] and preview["warnings_accepted"]
    assert "GENERATED_REVIEW" in preview["warning_codes"]
    assert bridge.publish(str(collection.id), 1, preview["handle"])["status"] == "COMMITTED"


def test_historical_details_and_rebuild_frozen(
    publications: tuple[Publications, Collection], tmp_path: Path
) -> None:
    service, collection = publications
    bridge = PublicationReview(service)
    preview = bridge.prepare(str(collection.id))
    bridge.publish(str(collection.id), 1, preview["handle"])
    saved = tree_files(folder(service, collection, 1))
    part = service.publisher.catalogue.require(Part, collection.part_ids[0])
    service.publisher.catalogue.save(replace(part, name="Changed"))
    assert bridge.details(str(collection.id), 1)["parts"][0]["name"] == part.name
    result = bridge.rebuild(str(collection.id), 1, str(tmp_path / "new"))
    assert result["rebuilt"]
    assert tree_files(tmp_path / "new") == {
        k.removeprefix("artifacts/"): v for k, v in saved.items() if k.startswith("artifacts/")
    }
    assert tree_files(folder(service, collection, 1)) == saved


@pytest.mark.parametrize(
    "params",
    [
        {"id": "/tmp"},
        {"id": "0" * 32, "offset": True},
        {"id": "0" * 32, "manifest": {}},
        {"id": "0" * 32, "destination": "/tmp"},
    ],
)
def test_strict_publication_query(params: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        validate("publication_history", params)


def test_ipc_readonly_busy_and_restore_guards(
    publications: tuple[Publications, Collection], engine: Engine
) -> None:
    from types import SimpleNamespace

    service, collection = publications
    bridge = PublicationReview(service)
    reader = CatalogueReader(
        service.publisher.catalogue,
        service.publisher.catalogue.repository,
        SqliteDocumentation(engine),
    )
    preview = bridge.prepare(str(collection.id))
    request = json.dumps(
        {
            "protocol_version": 1,
            "request_id": "test",
            "method": "publication_publish",
            "params": {"id": str(collection.id), "version": 1, "handle": preview["handle"]},
        }
    ).encode()
    assert respond(request, reader, publications=bridge)["error"]["code"] == "READ_ONLY"
    # Minimal host states exercise only the guards, before any ingestion method.
    busy: Any = SimpleNamespace(preparation="active")
    assert respond(request, reader, ingestion=busy, publications=bridge)["error"]["code"] == "BUSY"
    writable: Any = SimpleNamespace(preparation=None)
    restored: Any = SimpleNamespace(requires_restart=True)
    assert (
        respond(request, reader, ingestion=writable, workspace=restored, publications=bridge)[
            "error"
        ]["code"]
        == "READ_ONLY"
    )
    assert service.list_publications() == ()


def test_builder_refusal_not_bypassed_by_accepted_warning(tmp_path: Path, engine: Engine) -> None:
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications
    from tests.test_publisher import local_probe
    from tests.test_validation import FOOTPRINT, setup_case

    fp = (
        FOOTPRINT[:-1]
        + '(model "absent.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))'
    )
    validation, _, _, _, collection, _ = setup_case(tmp_path, engine, footprint=fp)
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    builder = LocalLibraryBuilder(
        local_probe(validation).store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"
    )
    service = Publications(
        LocalPublisher(validation.catalogue, validation, builder),
        LocalPublications(tmp_path / "data/publications", builder),
    )
    bridge = PublicationReview(service)
    preview = bridge.prepare(str(collection.id))
    with pytest.raises(DomainError):
        bridge.publish(str(collection.id), 1, preview["handle"])
    assert bridge.status(str(collection.id), 1)["status"] == "ABSENT"


def test_real_readonly_process_preserves_publications(
    publications: tuple[Publications, Collection], tmp_path: Path, engine: Engine
) -> None:
    import shutil
    import subprocess
    import sys

    from tests.test_headless import hashes, request

    service, collection = publications
    service.publish(collection, 1)
    # The M7 fixture stores history under data/; the copy root owns publications/.
    shutil.copytree(tmp_path / "data/publications", tmp_path / "publications")
    engine.dispose()
    (tmp_path / "TECH01_COPY.json").write_text(
        json.dumps(
            {"format": "fabparts-tech01-copy/1", "source": str(tmp_path.parent / "historical")}
        )
    )
    before = hashes(tmp_path)
    identity = {"id": str(collection.id)}
    frames = b"".join(
        [
            request("health"),
            request("publication_history", identity),
            request("publication_verify", {**identity, "version": 1}),
            request("publication_publish", {**identity, "version": 2, "handle": "a" * 48}),
            request(
                "publication_rebuild",
                {**identity, "version": 1, "destination": str(tmp_path / "denied")},
            ),
            request("shutdown"),
        ]
    )
    result = subprocess.run(
        [sys.executable, "-m", "kipartmanager.headless", "--data-dir", str(tmp_path)],
        input=frames,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0]["result"]["read_only"] and not replies[0]["result"]["qt_loaded"]
    assert replies[1]["result"]["total"] == 1
    assert replies[2]["result"]["verification"] == "PASS"
    assert replies[3]["error"]["code"] == replies[4]["error"]["code"] == "READ_ONLY"
    assert hashes(tmp_path) == before
