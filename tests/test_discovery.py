"""Synthetic relationships, explicit metadata acceptance and no discovery writes."""

from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from kipartmanager.application.discovery import LocalDiscovery
from kipartmanager.application.ingestion import Ingestion, IngestionFields
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.documentation import (
    FieldValue,
    MetadataField,
    MetadataProposal,
    MetadataSource,
)
from kipartmanager.domain.entities import DomainError, Package, Part
from kipartmanager.domain.kicad import LibraryRoots
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from tests.test_ingestion import ingestion as ingestion
from tests.test_previews import FOOTPRINT, SYMBOL


def configure(service: Ingestion, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    (root / "symbols").mkdir(parents=True)
    (root / "footprints/Pkg.pretty").mkdir(parents=True)
    (root / "models/Pkg.3dshapes").mkdir(parents=True)
    # Two synthetically named electronic variants, each declaring its own package.
    text = SYMBOL.replace('(symbol "Base"', '(symbol "Base" (property "Footprint" "Pkg:SOIC")')
    text = (
        text.replace('"Child"', '"NE555D"')[:-1]
        + '(symbol "NE555D_ALT" (extends "Base") (property "Footprint" "Pkg:DIP")))'
    )
    text = text[:-1] + '(symbol "LM1117MP-3.3" (extends "Base")))'
    (root / "symbols/Timer.kicad_sym").write_text(text)
    for name in ("SOIC", "DIP"):
        footprint = FOOTPRINT.replace('"SOIC fixture"', '"' + name + '"')
        footprint = (
            footprint[:-1] + '(model "${KICAD10_3DMODEL_DIR}/Pkg.3dshapes/shared.step" '
            "(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))"
        )
        (root / f"footprints/Pkg.pretty/{name}.kicad_mod").write_text(footprint)
    step = (Path(__file__).parent / "fixtures/models/box.step").read_bytes()
    (root / "models/Pkg.3dshapes/shared.step").write_bytes(step)
    (root / "models/Wrong.3dshapes").mkdir()
    (root / "models/Wrong.3dshapes/shared.step").write_bytes(step)
    index = LocalKiCadIndex(tmp_path / "sandbox")
    libraries = KiCadLibraries(index)
    libraries.configure(
        LibraryRoots(str(root / "symbols"), str(root / "footprints"), str(root / "models"))
    )
    report = libraries.rebuild()
    assert not report.issues
    assert isinstance(service.catalogue.repository, SqliteCatalogue)
    assert isinstance(service.store, LocalAssetStore)
    service.libraries = libraries
    service.resolver = LocalResolver(service.catalogue, service.catalogue.repository, libraries)
    service.discovery = LocalDiscovery(
        service.catalogue,
        service.documentation,
        service.resolver,
        LocalResourceProbe(service.store, index),
    )


def fields(service: Ingestion, reference: str = "NE555D") -> IngestionFields:
    session = service.begin()
    return IngestionFields(reference=reference, collections=(session["collections"][0]["id"],))


def discover(service: Ingestion, info: IngestionFields) -> dict[str, dict[str, Any]]:
    assert service.preparation
    return {
        role: service.discover(service.preparation.handle, info, role)
        for role in ("SYMBOL", "FOOTPRINT", "MODEL_3D", "DATASHEET")
    }


def test_official_variants_links_and_models_are_suggestions_only(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    configure(ingestion, tmp_path)
    info = fields(ingestion)
    before = ingestion.catalogue.list_entities(Part)
    result = discover(ingestion, info)
    assert {c["name"] for c in result["SYMBOL"]["candidates"]} == {
        "Timer:NE555D",
        "Timer:NE555D_ALT",
    }
    assert {
        c["name"] for c in result["FOOTPRINT"]["candidates"] if c["reason"] == "symbol_footprint"
    } == {"Pkg:SOIC", "Pkg:DIP"}
    assert [c["name"] for c in result["MODEL_3D"]["candidates"]] == ["Pkg.3dshapes/shared.step"]
    assert ingestion.catalogue.list_entities(Part) == before
    assert not ingestion.catalogue.list_entities(Package)
    assert ingestion.preparation
    preview = ingestion.preview(
        ingestion.preparation.handle, result["SYMBOL"]["candidates"][0]["token"]
    )
    assert preview["status"] == "ready" and not preview["selected"]


@pytest.mark.parametrize("reference", ["unknown-qual06", "10 kΩ 0603", "LM1117MP-3.3"])
def test_absent_index_or_unknown_reference_does_not_invent_assets(
    ingestion: Ingestion, reference: str
) -> None:
    result = discover(ingestion, fields(ingestion, reference))
    assert all(not stage["candidates"] for stage in result.values())
    assert "INDEX_UNAVAILABLE" in result["SYMBOL"]["notices"]
    assert not ingestion.catalogue.list_entities(Part)


def test_profile_suggestions_persist_only_explicit_fields_with_source(ingestion: Ingestion) -> None:
    part = Part(name="NE555D")
    ingestion.catalogue.save(part)
    identity = ingestion.documentation.identification(part.id)
    identity = identity.accept(
        MetadataProposal(
            MetadataSource("Known local profile", "fixture"),
            (
                FieldValue(MetadataField.MPN, "NE555D"),
                FieldValue(MetadataField.MANUFACTURER, "Known maker"),
            ),
        ),
        (MetadataField.MPN, MetadataField.MANUFACTURER),
        replace_existing=False,
        recorded_at="2026-10-26T12:00:00+00:00",
    )
    ingestion.documentation.save_identification(
        identity, ingestion.documentation.identification(part.id)
    )
    info = fields(ingestion)
    result = discover(ingestion, info)
    assert len(ingestion.catalogue.list_entities(Part)) == 1
    suggestions = result["SYMBOL"]["metadata"]
    chosen = next(m for m in suggestions if m["field"] == "mpn")
    info = replace(info, reference="My NE555D variant", mpn="NE555D", manufacturer="Known maker")
    assert ingestion.preparation
    outcome = ingestion.commit(
        ingestion.preparation.handle,
        str(ingestion.preparation.operation_id),
        info,
        {},
        action="variant",
        metadata={"mpn": chosen["token"]},
    )
    saved = ingestion.documentation.identification(UUID(outcome["part_id"]))
    assert saved.value(MetadataField.MANUFACTURER) == "Known maker"
    events = {v.field: event.source for event in saved.history for v in event.after}
    assert events[MetadataField.MPN].reference.startswith(f"fabparts:part:{part.id}:")
    assert events[MetadataField.MANUFACTURER].label == "Saisie utilisateur"


def test_stale_discovery_context_and_forged_metadata_are_refused(ingestion: Ingestion) -> None:
    info = fields(ingestion)
    assert ingestion.preparation
    prep = ingestion.preparation
    ingestion.discover(prep.handle, info, "SYMBOL")
    with pytest.raises(DomainError):
        ingestion.discover(prep.handle, replace(info, reference="Other"), "FOOTPRINT")
    with pytest.raises(DomainError):
        ingestion.commit(prep.handle, str(prep.operation_id), info, {}, metadata={"mpn": "a" * 48})
    assert not ingestion.catalogue.list_entities(Part)


def test_user_supplied_and_official_candidates_coexist_without_replacement(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    from tests.test_ingestion import stage

    configure(ingestion, tmp_path)
    info = fields(ingestion)
    assert ingestion.preparation
    user = tmp_path / "provided.kicad_sym"
    user.write_text(SYMBOL)
    stage(ingestion, ingestion.preparation.handle, user)
    result = discover(ingestion, info)["SYMBOL"]
    assert any(c["storage"] == "staged" and c["name"] == "Child" for c in result["candidates"])
    assert any(
        c["storage"] == "reference" and c["name"] == "Timer:NE555D" for c in result["candidates"]
    )
    assert user.read_text() == SYMBOL
    assert not ingestion.catalogue.list_entities(Part)


def test_pin_pad_mismatch_is_not_presented_as_declared_compatible_link(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    configure(ingestion, tmp_path)
    path = tmp_path / "corpus/footprints/Pkg.pretty/SOIC.kicad_mod"
    path.write_text(path.read_text().replace('(pad "2"', '(pad "9"'))
    assert ingestion.libraries
    ingestion.libraries.rebuild()
    result = discover(ingestion, fields(ingestion))
    assert not any(
        c["name"] == "Pkg:SOIC" and c["reason"] == "symbol_footprint"
        for c in result["FOOTPRINT"]["candidates"]
    )


def test_discovery_protocol_readonly_and_unknown_field_guards(ingestion: Ingestion) -> None:
    import json

    from kipartmanager.headless_ipc import respond

    def call(params: dict[str, Any], writable: bool) -> dict[str, Any]:
        return respond(
            json.dumps(
                {
                    "protocol_version": 1,
                    "request_id": "discovery",
                    "method": "ingestion_discover",
                    "params": params,
                }
            ).encode(),
            ingestion.previews.catalogue,
            ingestion.previews,
            ingestion if writable else None,
        )

    assert call({}, False)["error"]["code"] == "READ_ONLY"
    assert call({"path": "/anywhere"}, True)["error"]["code"] == "INVALID_PARAMS"


def test_inherited_symbol_resolves_its_parent_footprint_without_selection(
    ingestion: Ingestion, tmp_path: Path
) -> None:
    configure(ingestion, tmp_path)
    result = discover(ingestion, fields(ingestion, "LM1117MP-3.3"))
    assert result["SYMBOL"]["candidates"][0]["match"] == "exact"
    assert result["FOOTPRINT"]["candidates"][0]["reason"] == "symbol_footprint"
    assert result["MODEL_3D"]["candidates"][0]["reason"] == "footprint_model"


def test_generic_resistor_reuses_catalogue_package_without_network(
    ingestion: Ingestion, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_ingestion import stage

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Discovery must not connect")

    monkeypatch.setattr("socket.create_connection", no_network)
    begin = ingestion.begin()
    stage(
        ingestion, begin["preparation"], Path(__file__).parent / "fixtures/previews/R0603.kicad_mod"
    )
    token = ingestion.search(begin["preparation"], "FOOTPRINT")["candidates"][0]["token"]
    info = IngestionFields(
        reference="10 kΩ 0603", package_name="0603", collections=(begin["collections"][0]["id"],)
    )
    ingestion.commit(begin["preparation"], begin["operation_id"], info, {"FOOTPRINT": token})
    result = discover(ingestion, fields(ingestion, "10 kΩ 0603"))
    candidate = result["FOOTPRINT"]["candidates"][0]
    assert candidate["storage"] == "managed" and candidate["reason"] == "catalogue_choice"
    assert result["SYMBOL"]["packages"][0]["name"] == "0603"
    assert len(ingestion.catalogue.list_entities(Part)) == 1


def test_short_catalogue_names_do_not_match_arbitrary_reference_substrings(
    ingestion: Ingestion,
) -> None:
    ingestion.catalogue.save(Part(name="R"))
    assert ingestion.discovery.similar("STRANGE-UNKNOWN", "") == []
    assert [p.name for p in ingestion.discovery.similar("R", "")] == ["R"]
