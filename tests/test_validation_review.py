"""M5 evidence projection, strict report review and readonly IPC composition."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.validation import LocalValidation
from kipartmanager.application.validation_review import ReportChanged, ValidationReview
from kipartmanager.domain.entities import AssetType, Collection, Part, PartState
from kipartmanager.headless_ipc import respond
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
from kipartmanager.validation_ipc import validate
from tests.test_validation import FOOTPRINT, SYMBOL, setup_case


def test_incomplete_and_preview_or_selection_never_prove_readiness(
    tmp_path: Path, engine: Engine
) -> None:
    local, _, part, _, _, _ = setup_case(tmp_path, engine)
    review = ValidationReview(local)
    assert review.get(part)["readiness"] == "INCOMPLETE"  # both resources already selected
    other = Part(name="Empty")
    local.catalogue.save(other)
    result = review.run(other)
    assert result["readiness"] == "INCOMPLETE" and result["state"] == "ERROR"
    assert result["report"]["counts"]["ERROR"] >= 3


def test_valid_symbol_without_package_proves_only_schematic(tmp_path: Path, engine: Engine) -> None:
    local, _, part, _, _, _ = setup_case(tmp_path, engine)
    part = replace(local.catalogue.require(Part, part.id), package_id=None)
    local.catalogue.save(part)
    result = ValidationReview(local).run(part)
    assert result["state"] == "ERROR" and result["readiness"] == "SCHEMATIC"
    assert not result["eligible"]
    assert {f["role"] for f in result["findings"]} == {"SYMBOL", "GLOBAL"}


def test_pcb_pass_optional_resources_and_business_state_unchanged(
    tmp_path: Path, engine: Engine
) -> None:
    local, _, part, _, _, _ = setup_case(tmp_path, engine)
    result = ValidationReview(local).run(part)
    assert result["state"] == "PASS" and result["readiness"] == "PCB"
    assert result["eligible"] and result["handle"] is None
    assert local.catalogue.require(Part, part.id).state is PartState.DRAFT
    assert {f["role"] for f in result["findings"]} >= {"SYMBOL", "FOOTPRINT", "GLOBAL"}
    reopened = ValidationReview(
        LocalValidation(local.catalogue, local.probe, SqliteValidationReports(engine))
    )
    assert reopened.get(part)["report"] == result["report"]
    assert reopened.get(part)["readiness"] == "PCB"


def test_pin_pad_mismatch_is_error_but_valid_symbol_remains_schematic(
    tmp_path: Path, engine: Engine
) -> None:
    local, _, part, _, _, _ = setup_case(
        tmp_path, engine, symbol=SYMBOL.replace('(number "2")', '(number "9")')
    )
    result = ValidationReview(local).run(part)
    assert result["readiness"] == "SCHEMATIC" and not result["eligible"]
    assert any(f["code"] == "PIN_PAD" and f["level"] == "ERROR" for f in result["findings"])


@pytest.mark.parametrize("role", [AssetType.SYMBOL, AssetType.FOOTPRINT])
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_resource_damage_invalidates_all_ready_statuses(
    tmp_path: Path, engine: Engine, role: AssetType, damage: str
) -> None:
    local, _, part, _, _, assets = setup_case(tmp_path, engine)
    review = ValidationReview(local)
    assert review.run(part)["readiness"] == "PCB"
    asset = next(a for a in assets if a.asset_type is role)
    assert asset.file is not None and isinstance(local.probe, LocalResourceProbe)
    path = local.probe.store.root / asset.file.relative_key
    path.unlink() if damage == "missing" else path.write_bytes(b"broken")
    result = review.get(part)
    assert result["state"] == "STALE" and result["readiness"] == "INCOMPLETE"
    result = review.run(part)
    assert result["state"] == "ERROR" and not result["eligible"]
    assert result["readiness"] == ("SCHEMATIC" if role is AssetType.FOOTPRINT else "INCOMPLETE")


def warning_case(tmp_path: Path, engine: Engine) -> tuple[ValidationReview, Part, Collection]:
    footprint = FOOTPRINT[:-1] + ' (pad "3" smd rect (at 2 0) (size 1 1) (layers "F.Cu")))'
    local, _, part, _, collection, _ = setup_case(tmp_path, engine, footprint=footprint)
    return ValidationReview(local), part, collection


def test_warning_acceptance_requires_the_viewed_exact_current_report(
    tmp_path: Path, engine: Engine
) -> None:
    review, part, _ = warning_case(tmp_path, engine)
    with pytest.raises(ReportChanged):
        review.accept(part, "a" * 48)
    result = review.run(part)
    assert result["state"] == "WARNING" and result["readiness"] == "SCHEMATIC"
    assert not result["eligible"] and not result["report"]["warnings_accepted"]
    with pytest.raises(ReportChanged):
        review.accept(part, "a" * 48)
    result = review.get(part)
    accepted = review.accept(part, result["handle"])
    assert accepted["readiness"] == "PCB" and accepted["report"]["warnings_accepted"]
    with pytest.raises(ReportChanged):
        review.accept(part, result["handle"])
    again = review.run(part)
    assert not again["report"]["warnings_accepted"] and not again["eligible"]


@pytest.mark.parametrize("change", ["data", "report", "session"])
def test_stale_or_replaced_report_and_old_session_cannot_be_accepted(
    tmp_path: Path, engine: Engine, change: str
) -> None:
    review, part, _ = warning_case(tmp_path, engine)
    token = review.run(part)["handle"]
    if change == "data":
        review.validation.catalogue.save(
            replace(review.validation.catalogue.require(Part, part.id), description="Changed")
        )
    elif change == "report":
        review.validation.validate(
            part
        )  # even identical findings: this is a different displayed report
    else:
        review = ValidationReview(review.validation)
    with pytest.raises(ReportChanged):
        review.accept(part, token)
    assert not review.validation.qualification(part).eligible


def test_deprecated_or_generated_symbol_cannot_be_unconditionally_schematic(
    tmp_path: Path, engine: Engine
) -> None:
    from kipartmanager.domain.entities import AssetOrigin

    local, _, part, _, _, assets = setup_case(tmp_path, engine)
    symbol = next(a for a in assets if a.asset_type is AssetType.SYMBOL)
    local.catalogue.save(replace(symbol, origin=AssetOrigin.GENERATED_AI))
    review = ValidationReview(local)
    result = review.run(part)
    assert result["state"] == "WARNING" and result["readiness"] == "INCOMPLETE"
    assert review.accept(part, result["handle"])["readiness"] == "PCB"
    local.catalogue.save(
        replace(local.catalogue.require(Part, part.id), state=PartState.DEPRECATED)
    )
    assert review.get(part)["readiness"] == "INCOMPLETE"
    assert review.run(part)["readiness"] == "INCOMPLETE"


def test_collection_reports_members_blockers_warnings_and_stale_membership(
    tmp_path: Path, engine: Engine
) -> None:
    review, part, collection = warning_case(tmp_path, engine)
    other = Part(name="Incomplete member")
    review.validation.catalogue.save(other)
    collection = replace(collection, part_ids=(part.id, other.id))
    review.validation.catalogue.save(collection)
    result = review.run(collection)
    assert result["total_members"] == 2 and result["state"] == "ERROR" and not result["eligible"]
    by_id = {member["id"]: member for member in result["members"]}
    assert by_id[str(part.id)]["warnings"] == 1
    assert by_id[str(other.id)]["errors"] >= 3
    assert all(f["part_id"] in {str(part.id), str(other.id)} for f in result["findings"])
    review.validation.catalogue.save(replace(collection, part_ids=(part.id,)))
    assert review.get(collection)["state"] == "STALE"
    result = review.run(collection)
    assert result["state"] == "WARNING"
    assert review.accept(collection, result["handle"])["eligible"]
    # A collection report does not silently create Part reports.
    assert review.validation.repository.load_report(part) is None


def test_collection_pagination_and_bounded_capabilities(tmp_path: Path, engine: Engine) -> None:
    local, _, part, _, collection, _ = setup_case(tmp_path, engine)
    parts = [part] + [replace(part, id=uuid4(), name=f"Part {n}", asset_ids=()) for n in range(55)]
    for member in parts[1:]:
        local.catalogue.save(member)
    collection = replace(collection, part_ids=tuple(p.id for p in parts))
    local.catalogue.save(collection)
    review = ValidationReview(local)
    result = review.run(collection)
    assert result["total_members"] == 56 and len(result["members"]) == 50
    assert result["total_findings"] > 100 and len(result["findings"]) == 100
    result = review.get(collection, 100, 50)
    assert result["offset"] == 100 and len(result["members"]) == 6


def test_ipc_readonly_mutations_and_report_fields_are_denied(
    tmp_path: Path, engine: Engine
) -> None:
    local, _, part, _, _, _ = setup_case(tmp_path, engine)
    review = ValidationReview(local)
    review.run(part)
    reader = CatalogueReader(
        local.catalogue, local.catalogue.repository, SqliteDocumentation(engine)
    )

    def call(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return respond(
            json.dumps(
                {"protocol_version": 1, "request_id": "v", "method": method, "params": params}
            ).encode(),
            reader,
            review=review,
        )

    params = {"kind": "Part", "id": str(part.id)}
    assert call("validation_get", params)["result"]["readiness"] == "PCB"
    assert call("validation_run", params)["error"]["code"] == "READ_ONLY"
    assert call("validation_accept", {**params, "handle": "a" * 48})["error"]["code"] == "READ_ONLY"
    patches: list[dict[str, Any]] = [
        {"report": {}},
        {"fingerprint": "a" * 64},
        {"offset": True},
        {"kind": "Asset"},
        {"id": "/path"},
        {"kind": []},
    ]
    for patch in patches:
        assert call("validation_get", {**params, **patch})["error"]["code"] == "INVALID_PARAMS"
    for method in ("validation_run", "validation_accept"):
        with pytest.raises(ValueError):
            validate(method, {**params, "accept_warnings": True})


def test_real_readonly_process_reads_saved_evidence_without_writing(
    tmp_path: Path, engine: Engine
) -> None:
    import subprocess
    import sys

    from tests.test_headless import hashes, request

    local, _, part, _, _, _ = setup_case(tmp_path, engine)
    local.validate(part)
    engine.dispose()
    (tmp_path / "TECH01_COPY.json").write_text(
        json.dumps(
            {"format": "fabparts-tech01-copy/1", "source": str(tmp_path.parent / "historical")}
        )
    )
    before = hashes(tmp_path)
    params = {"kind": "Part", "id": str(part.id)}
    frames = b"".join(
        [
            request("health"),
            request("validation_get", params),
            request("validation_run", params),
            request("validation_accept", {**params, "handle": "a" * 48}),
            request("shutdown"),
        ]
    )
    process = subprocess.run(
        [sys.executable, "-m", "kipartmanager.headless", "--data-dir", str(tmp_path)],
        input=frames,
        capture_output=True,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    assert replies[0]["result"]["read_only"] and not replies[0]["result"]["qt_loaded"]
    assert replies[1]["result"]["readiness"] == "PCB"
    assert replies[2]["error"]["code"] == replies[3]["error"]["code"] == "READ_ONLY"
    assert hashes(tmp_path) == before


def test_personal_report_survives_backup_restore_and_restart(tmp_path: Path) -> None:
    from uuid import UUID

    from kipartmanager.application.catalogue import Catalogue
    from kipartmanager.headless import open_personal_workspace
    from kipartmanager.infrastructure.asset_store import LocalAssetStore
    from kipartmanager.infrastructure.catalogue import SqliteCatalogue
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from tests.test_user_workspace import populate

    def review_for(workspace: Any) -> ValidationReview:
        catalogue = Catalogue(SqliteCatalogue(workspace.engine))
        return ValidationReview(
            LocalValidation(
                catalogue,
                LocalResourceProbe(
                    LocalAssetStore(workspace.root / "assets"), LocalKiCadIndex(workspace.root)
                ),
                SqliteValidationReports(workspace.engine),
            )
        )

    home = tmp_path / "personal"
    workspace = open_personal_workspace(home)
    identity, _ = populate(workspace)
    review = review_for(workspace)
    part = review.validation.catalogue.require(Part, UUID(identity))
    result = review.run(part)
    assert result["state"] == "WARNING"
    result = review.accept(part, result["handle"])
    assert result["readiness"] == "PCB"
    source = Path(workspace.backup()["path"])
    workspace.restore(workspace.verify(source)["handle"])
    workspace.close()
    workspace = open_personal_workspace(home)
    try:
        again = review_for(workspace).get(part)
        assert again["report"] == result["report"] and again["readiness"] == "PCB"
    finally:
        workspace.close()


def test_symbol_warnings_can_be_reviewed_despite_pcb_errors_as_m5_allows(
    tmp_path: Path, engine: Engine
) -> None:
    from kipartmanager.domain.entities import AssetOrigin

    local, _, part, _, _, assets = setup_case(tmp_path, engine)
    symbol = next(asset for asset in assets if asset.asset_type is AssetType.SYMBOL)
    local.catalogue.save(replace(symbol, origin=AssetOrigin.GENERATED_PARAMETRIC))
    part = replace(local.catalogue.require(Part, part.id), package_id=None)
    local.catalogue.save(part)
    review = ValidationReview(local)
    result = review.run(part)
    assert result["state"] == "ERROR" and result["handle"] and result["readiness"] == "INCOMPLETE"
    result = review.accept(part, result["handle"])
    assert result["state"] == "ERROR" and not result["eligible"]
    assert result["readiness"] == "SCHEMATIC" and result["report"]["warnings_accepted"]


def test_personal_validation_ipc_busy_and_restore_restart_gate(tmp_path: Path) -> None:
    from uuid import UUID

    from kipartmanager.headless import open_personal_workspace
    from kipartmanager.infrastructure.asset_store import LocalAssetStore
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from tests.test_user_workspace import close, compose, populate

    workspace = open_personal_workspace(tmp_path / "personal")
    identity, _ = populate(workspace)
    service = compose(workspace)
    reader = CatalogueReader(service.catalogue, service.catalogue.repository, service.documentation)
    review = ValidationReview(
        LocalValidation(
            service.catalogue,
            LocalResourceProbe(
                LocalAssetStore(workspace.root / "assets"), LocalKiCadIndex(workspace.root)
            ),
            SqliteValidationReports(workspace.engine),
        )
    )

    def call(method: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"kind": "Part", "id": identity, **(extra or {})}
        return respond(
            json.dumps(
                {"protocol_version": 1, "request_id": "v", "method": method, "params": params}
            ).encode(),
            reader,
            service.previews,
            service,
            "0008_ingestion_operations",
            workspace,
            review,
        )

    try:
        result = call("validation_run")["result"]
        assert result["state"] == "WARNING"
        service.begin()
        assert call("validation_accept", {"handle": result["handle"]})["error"]["code"] == "BUSY"
        service.close()
        assert call("validation_accept", {"handle": result["handle"]})["result"]["eligible"]
        source = Path(workspace.backup()["path"])
        workspace.restore(workspace.verify(source)["handle"])
        assert call("validation_run")["error"]["code"] == "READ_ONLY"
        assert review.validation.catalogue.require(Part, UUID(identity)).state is PartState.DRAFT
    finally:
        close(service, workspace)
