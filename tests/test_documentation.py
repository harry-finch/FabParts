"""M10 durable enrichment, explicit conflicts and additive PDF documentation."""

import json
import socket
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.documentation import (
    DocumentDetails,
    FieldValue,
    Identification,
    MetadataField,
    MetadataProposal,
    MetadataSource,
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import LocalProposalReader, SqliteDocumentation
from kipartmanager.infrastructure.models import DocumentRow, IdentificationRow

PDF = b"%PDF-1.4\nfixture preserved bytes\n%%EOF"
SOURCE = MetadataSource("Saisie locale", "user:local")
MANUFACTURER = MetadataSource(
    "Constructeur déclaré", "https://docs.maker.example/r.pdf", AssetOrigin.MANUFACTURER
)


class FixtureManufacturer:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failure = False

    def download(self, url: str, config: DatasheetConfiguration) -> DatasheetDownload:
        config.authorize(url)
        self.calls.append(url)
        if self.failure:
            raise DomainError("Constructeur indisponible")
        return DatasheetDownload(url, PDF)


@pytest.fixture
def setup(engine: Engine, tmp_path: Path) -> tuple[Documentation, Part, FixtureManufacturer]:
    store = LocalAssetStore(tmp_path / "assets")
    catalogue = Catalogue(SqliteCatalogue(engine), store)
    part = Part(name="R", description="Description saisie à conserver")
    catalogue.save(part)
    provider = FixtureManufacturer()
    service = Documentation(
        catalogue,
        SqliteDocumentation(engine),
        LocalProposalReader(),
        ManufacturerSettings(tmp_path),
        provider,
    )
    return service, part, provider


def proposal(value: str, source: MetadataSource = SOURCE) -> MetadataProposal:
    return MetadataProposal(source, (FieldValue(MetadataField.MANUFACTURER, value),))


def test_acceptance_history_partial_conflicts_and_restart(
    setup: tuple[Documentation, Part, FixtureManufacturer],
    engine: Engine,
    tmp_path: Path,
) -> None:
    service, part, _ = setup
    current = service.identification(part.id)
    assert current == Identification(part.id)
    first = service.accept(current, proposal("User manufacturer"), (MetadataField.MANUFACTURER,))
    proposed = MetadataProposal(
        MANUFACTURER,
        (
            FieldValue(MetadataField.MANUFACTURER, "Maker"),
            FieldValue(MetadataField.MPN, "R-123"),
        ),
    )
    assert first.conflicts(proposed) == (MetadataField.MANUFACTURER,)
    with pytest.raises(DomainError, match="Confirmer"):
        service.accept(first, proposed, (MetadataField.MANUFACTURER,))
    second = service.accept(first, proposed, (MetadataField.MPN,))
    assert second.value(MetadataField.MANUFACTURER) == "User manufacturer"
    assert second.value(MetadataField.MPN) == "R-123"
    final = service.accept(second, proposed, (MetadataField.MANUFACTURER,), replace_existing=True)
    assert len(final.history) == final.revision == 3
    assert final.history[-1].before[0].value == "User manufacturer"
    assert final.history[-1].source == MANUFACTURER
    assert service.catalogue.require(Part, part.id) == part
    reopened = Documentation(
        service.catalogue,
        SqliteDocumentation(engine),
        LocalProposalReader(),
        ManufacturerSettings(tmp_path),
    )
    assert reopened.identification(part.id) == final


def test_stale_preview_never_overwrites(
    setup: tuple[Documentation, Part, FixtureManufacturer],
) -> None:
    service, part, _ = setup
    expected = service.identification(part.id)
    saved = service.accept(expected, proposal("A"), (MetadataField.MANUFACTURER,))
    with pytest.raises(DomainError, match="modifiée"):
        service.accept(
            expected, proposal("B"), (MetadataField.MANUFACTURER,), replace_existing=True
        )
    assert service.identification(part.id) == saved


@pytest.mark.parametrize(
    "fields", [(), (MetadataField.MPN,), (MetadataField.MANUFACTURER, MetadataField.MANUFACTURER)]
)
def test_invalid_acceptance(
    setup: tuple[Documentation, Part, FixtureManufacturer], fields: tuple[MetadataField, ...]
) -> None:
    service, part, _ = setup
    with pytest.raises(DomainError):
        service.accept(service.identification(part.id), proposal("Maker"), fields)
    assert service.identification(part.id).history == ()


def test_existing_and_new_pdfs_preserved_without_changing_choice(
    setup: tuple[Documentation, Part, FixtureManufacturer],
    tmp_path: Path,
) -> None:
    service, part, _ = setup
    assert service.catalogue.store is not None
    imports = AssetImports(service.catalogue, service.catalogue.store)
    original = imports.import_content(
        PDF,
        "original.pdf",
        name="Original",
        origin=AssetOrigin.USER_PROVIDED,
        source_reference="user original",
    )
    assert isinstance(service.catalogue.repository, SqliteCatalogue)
    resolver = LocalResolver(service.catalogue, service.catalogue.repository)
    candidate = resolver.search(part, AssetType.DATASHEET, "Original").candidates[0]
    resolver.select(part, candidate)
    details = DocumentDetails("Datasheet v1", SOURCE, "1", "2026-10-01", "fr")
    first = service.add_existing(part.id, original.id, details)
    source = tmp_path / "v2.pdf"
    source.write_bytes(PDF + b"\nversion2")
    second = service.import_local(
        part.id, str(source), replace(details, title="Datasheet v2", revision="2")
    )
    assert service.catalogue.require(Asset, original.id) == original
    assert resolver.choices(part) == (candidate.choice,)
    current_part = service.catalogue.require(Part, part.id)
    assert set(current_part.asset_ids) == {original.id, second.asset_id}
    assert service.documents(part.id) == (first, second)
    output = tmp_path / "copy.pdf"
    service.retrieve(part.id, first.id, str(output))
    assert output.read_bytes() == PDF
    with pytest.raises(DomainError, match="existe"):
        service.retrieve(part.id, second.id, str(output))
    with pytest.raises(DomainError, match="déjà documenté"):
        service.add_existing(part.id, original.id, details)
    assert source.read_bytes() == PDF + b"\nversion2"


def test_remote_opt_in_provenance_failure_and_local_workflow(
    setup: tuple[Documentation, Part, FixtureManufacturer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, part, provider = setup
    url = MANUFACTURER.reference
    with pytest.raises(DomainError, match="désactivé"):
        service.download(url)
    assert provider.calls == []
    service.configure(DatasheetConfiguration(True, ("docs.maker.example",)))
    with pytest.raises(DomainError, match="autorisé"):
        service.download("https://other.example/r.pdf")
    assert provider.calls == []
    downloaded = service.download(url)
    record = service.import_download(
        part.id, downloaded, DocumentDetails("Maker PDF", MANUFACTURER, "A")
    )
    asset = service.catalogue.require(Asset, record.asset_id)
    assert asset.file is not None and asset.file.sha256 == downloaded.sha256
    assert asset.origin is AssetOrigin.MANUFACTURER and asset.source == url
    assert asset.validation_state == "UNCHECKED"
    provider.failure = True
    with pytest.raises(DomainError, match="indisponible"):
        service.download(url)
    service.configure(DatasheetConfiguration(False))

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    value = service.accept(
        service.identification(part.id), proposal("Local"), (MetadataField.MANUFACTURER,)
    )
    assert value.revision == 1 and service.documents(part.id) == (record,)
    assert len(service.catalogue.list_entities(Asset)) == 1


def test_absent_revoked_and_wrong_source_block_import(
    setup: tuple[Documentation, Part, FixtureManufacturer],
) -> None:
    service, part, _ = setup
    service.configure(DatasheetConfiguration(True, ("docs.maker.example",)))
    service.provider = None
    with pytest.raises(DomainError, match="absent"):
        service.download(MANUFACTURER.reference)
    data = DatasheetDownload(MANUFACTURER.reference, PDF)
    with pytest.raises(DomainError, match="provenance"):
        service.import_download(part.id, data, DocumentDetails("Sheet", SOURCE))
    service.configure(DatasheetConfiguration(True, ("other.example",)))
    with pytest.raises(DomainError, match="autorisé"):
        service.import_download(part.id, data, DocumentDetails("Sheet", MANUFACTURER))
    assert service.catalogue.list_entities(Asset) == [] and service.documents(part.id) == ()


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.maker.example/r.pdf",
        "https://evil.example/r.pdf",
        "https://docs.maker.example.evil.example/r.pdf",
        "https://user:pass@docs.maker.example/r.pdf",
        "https://docs.maker.example:8443/r.pdf",
        "https://docs.maker.example/r.pdf#fragment",
        "https://docs.maker.example/r\n.pdf",
    ],
)
def test_domain_authorization(url: str) -> None:
    with pytest.raises(DomainError):
        DatasheetConfiguration(True, ("docs.maker.example",)).authorize(url)


@pytest.mark.parametrize(
    "domain",
    [
        "*.maker.example",
        "https://maker.example",
        "127.0.0.1",
        "LOCALHOST",
        "localhost",
        "docs.localhost",
    ],
)
def test_invalid_authorized_hosts(domain: str) -> None:
    with pytest.raises(DomainError):
        DatasheetConfiguration(True, (domain,))


@pytest.mark.parametrize(
    "content", [b"", b"<html>login page</html>", b"%PDF-1.4" + b"x" * (32 * 1024 * 1024)]
)
def test_invalid_download(content: bytes) -> None:
    with pytest.raises(DomainError):
        DatasheetDownload(MANUFACTURER.reference, content)


def test_local_json_preview_and_malformed_sources(tmp_path: Path) -> None:
    reader = LocalProposalReader()
    source = tmp_path / "proposal.json"
    data = {
        "format": "kipart-identification/1",
        "source": {
            "label": "Maker",
            "reference": "manufacturer document",
            "origin": "MANUFACTURER",
        },
        "fields": {"mpn": "R-123", "manufacturer": "Maker"},
    }
    source.write_text(json.dumps(data))
    result = reader.read(str(source))
    assert result.source.origin is AssetOrigin.MANUFACTURER
    assert result.values[0] == FieldValue(MetadataField.MPN, "R-123")
    for malformed in (b"{}", b"not json", b"x" * 65537):
        source.write_bytes(malformed)
        with pytest.raises(DomainError):
            reader.read(str(source))
    data["fields"] = {"unknown": "value"}
    source.write_text(json.dumps(data))
    with pytest.raises(DomainError):
        reader.read(str(source))


def test_new_document_transaction_rolls_back_asset_and_association(
    setup: tuple[Documentation, Part, FixtureManufacturer],
    engine: Engine,
) -> None:
    service, part, _ = setup
    assert service.catalogue.store is not None
    file = service.catalogue.store.import_content(PDF, "first.pdf")
    asset = Asset(
        name="First", asset_type=AssetType.DATASHEET, origin=AssetOrigin.USER_PROVIDED, file=file
    )
    record = DocumentDetails("First", SOURCE).record(part.id, asset.id, "2026-10-01T00:00:00+00:00")
    service.repository.add_document(record, asset, new_asset=True)
    other = replace(asset, id=uuid4(), name="Second")
    failed_record = replace(record, asset_id=other.id)
    with pytest.raises(DomainError):
        service.repository.add_document(failed_record, other, new_asset=True)
    assert service.catalogue.repository.get(Asset, other.id) is None
    assert service.catalogue.require(Part, part.id).asset_ids == (asset.id,)
    assert service.documents(part.id) == (record,)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(IdentificationRow).values(part_id=part.id, revision=0, data_json="{}")
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(DocumentRow).values(
                id=uuid4(), part_id=uuid4(), asset_id=asset.id, data_json="{}"
            )
        )


def test_upgrade_m9_and_safe_downgrade(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "m9.sqlite3")
    try:
        migrate(engine, "0005_symbol_entry")
        part = Part(name="Existing", description="kept")
        SqliteCatalogue(engine).save(part)
        migrate(engine)
        assert SqliteCatalogue(engine).get(Part, part.id) == part
        repo = SqliteDocumentation(engine)
        assert repo.identification(part.id) == Identification(part.id)
        migrate(engine, "0005_symbol_entry", downgrade=True)
        assert SqliteCatalogue(engine).get(Part, part.id) == part
        migrate(engine)
        value = Identification(part.id).accept(
            proposal("Maker"),
            (MetadataField.MANUFACTURER,),
            replace_existing=False,
            recorded_at="2026-10-01T00:00:00+00:00",
        )
        repo.save_identification(value, Identification(part.id))
        with pytest.raises(RuntimeError, match="would be lost"):
            migrate(engine, "0005_symbol_entry", downgrade=True)
        assert repo.identification(part.id) == value
    finally:
        engine.dispose()


def test_documented_pdf_publishes_and_transfers_without_network(
    tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.infrastructure.bundles import LocalBundles
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications
    from tests.test_publisher import tree_files
    from tests.test_validation import setup_case

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    validation, resolver, part, _, collection, _ = setup_case(tmp_path, engine)
    assert isinstance(validation.catalogue.store, LocalAssetStore)
    service = Documentation(
        validation.catalogue,
        SqliteDocumentation(engine),
        LocalProposalReader(),
        ManufacturerSettings(tmp_path),
    )
    source = tmp_path / "original.pdf"
    source.write_bytes(PDF)
    record = service.import_local(
        part.id, str(source), DocumentDetails("PDF original", MANUFACTURER)
    )
    asset = service.catalogue.require(Asset, record.asset_id)
    candidate = next(
        c
        for c in resolver.search(part, AssetType.DATASHEET, "PDF original").candidates
        if c.asset and c.asset.id == asset.id
    )
    resolver.select(part, candidate)
    validation.validate(collection)
    validation.validate(collection, accept_warnings=True)
    validation.require_publishable(collection)
    root = tmp_path / "history"
    builder = LocalLibraryBuilder(validation.catalogue.store, LocalKiCadIndex(root), root)
    history = LocalPublications(root / "publications", builder)
    publications = Publications(LocalPublisher(validation.catalogue, validation, builder), history)
    publication = publications.publish(collection, 1)
    folder = history._folder(collection.id, 1)
    frozen = tree_files(folder)
    source.write_bytes(PDF + b"new revision")
    service.import_local(part.id, str(source), DocumentDetails("PDF new", SOURCE, "B"))
    service.accept(
        service.identification(part.id), proposal("Maker"), (MetadataField.MANUFACTURER,)
    )
    history.verify(publication)
    assert tree_files(folder) == frozen
    assert isinstance(validation.catalogue.repository, SqliteCatalogue)
    archive = tmp_path / "datasheet.kiparts"
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
        assert (transferred.file, transferred.source, transferred.origin) == (
            asset.file,
            asset.source,
            asset.origin,
        )
        assert len(target.repository.list_entities(Asset)) == 3
        target_history.verify(publication)
        rebuilt = target_history.rebuild(publication, str(tmp_path / "rebuilt"))
        assert PDF in tree_files(Path(rebuilt.destination)).values()
        # v1 bundles carry selected asset provenance, not the new local annotations.
        assert SqliteDocumentation(target_engine).documents(part.id) == ()
        assert SqliteDocumentation(target_engine).identification(part.id).revision == 0
    finally:
        target_engine.dispose()
