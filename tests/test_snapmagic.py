"""M10.5 normalized partner boundary, exact candidates, durable import and offline core."""

import hashlib
import io
import socket
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Engine, text

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.third_party_assets import ThirdPartyResolver
from kipartmanager.domain.asset_provenance import Redistribution
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.domain.third_party_assets import (
    AssetQuery,
    ProviderState,
    ThirdPartyCandidate,
    ThirdPartyConfiguration,
)
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.snapmagic import (
    EnvironmentCredential,
    SnapMagicAdapter,
    SnapMagicRateLimit,
    SnapMagicRecord,
    SnapMagicSettings,
    ThirdPartyInspector,
)
from tests.test_validation import FOOTPRINT, SYMBOL, setup_case

SECRET = "fixture-secret-never-persisted"
MPN = "STM32F103C8T6"
STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
WRL = b"#VRML V2.0 utf8\nShape {}"


class FixtureCredential:
    def __init__(self) -> None:
        self.value: str | None = SECRET

    def read(self) -> str | None:
        return self.value


class FixturePartner:
    """Internal contract fixture, NOT a representation of SnapMagic's HTTP schema."""

    def __init__(self) -> None:
        self.records: tuple[SnapMagicRecord, ...] = ()
        self.content = STEP
        self.calls: list[str] = []
        self.error: Exception | None = None

    def search(self, query: AssetQuery, credential: str) -> tuple[SnapMagicRecord, ...]:
        assert credential == SECRET
        self.calls.append("search")
        if self.error:
            raise self.error
        return self.records

    def download(self, candidate: ThirdPartyCandidate, credential: str) -> bytes:
        assert credential == SECRET
        self.calls.append("download")
        if self.error:
            raise self.error
        return self.content


def record(kind: AssetType = AssetType.MODEL_3D, **values: Any) -> SnapMagicRecord:
    filename = {
        AssetType.SYMBOL: "R.kicad_sym",
        AssetType.FOOTPRINT: "R.kicad_mod",
        AssetType.MODEL_3D: "STM32F103C8T6.step",
    }[kind]
    base = SnapMagicRecord(
        "fixture-123",
        kind,
        MPN,
        MPN,
        "STMicroelectronics",
        filename,
        "https://www.snapeda.com/parts/STM32F103C8T6/STMicroelectronics/view-part/",
        package="LQFP-48",
        license_name="Licence déclarée par la fixture, non vérifiée",
        license_url="https://www.snapeda.com/about/terms/",
        attribution="Fixture author",
    )
    return replace(base, **values)


@pytest.fixture
def setup(
    engine: Engine, tmp_path: Path
) -> tuple[ThirdPartyResolver, FixturePartner, FixtureCredential]:
    catalogue = Catalogue(SqliteCatalogue(engine), LocalAssetStore(tmp_path / "assets"))
    partner, credential = FixturePartner(), FixtureCredential()
    return (
        ThirdPartyResolver(
            catalogue,
            SnapMagicSettings(tmp_path),
            ThirdPartyInspector(),
            SnapMagicAdapter(credential, partner),
        ),
        partner,
        credential,
    )


def query(kind: AssetType = AssetType.MODEL_3D) -> AssetQuery:
    return AssetQuery(MPN, "STMicroelectronics", kind)


def enable(service: ThirdPartyResolver) -> None:
    service.configure(ThirdPartyConfiguration(True))


def test_disabled_absent_credential_and_missing_contract(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
) -> None:
    service, partner, credential = setup
    assert service.state() is ProviderState.DISABLED
    with pytest.raises(DomainError, match="désactivé"):
        service.search(query())
    enable(service)
    credential.value = None
    assert service.state() is ProviderState.NOT_CONFIGURED
    with pytest.raises(DomainError, match="non configuré"):
        service.search(query())
    credential.value = SECRET
    service.provider = SnapMagicAdapter(credential)
    assert service.state() is ProviderState.CONTRACT_REQUIRED
    with pytest.raises(DomainError, match="Contrat API"):
        service.search(query())
    service.provider = None
    assert service.state() is ProviderState.NOT_CONFIGURED
    assert partner.calls == []


def test_exact_mpn_multiple_empty_and_filtering(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
) -> None:
    service, partner, _ = setup
    enable(service)
    assert service.search(query()).candidates == ()
    partner.records = (
        record(),
        record(identity="second", filename="other.step"),
        record(identity="wrong-mpn", mpn=MPN + "B"),
        record(identity="wrong-maker", manufacturer="Other"),
        record(AssetType.SYMBOL, identity="wrong-kind"),
    )
    result = service.search(query())
    assert len(result.candidates) == 2
    assert "3 résultat" in result.notices[0]
    assert result.candidates[0].origin is AssetOrigin.TRUSTED_THIRD_PARTY
    assert result.candidates[0].redistribution is Redistribution.UNKNOWN
    assert service.catalogue.list_entities(Asset) == []
    assert partner.calls == ["search", "search"]


@pytest.mark.parametrize(
    "error,expected",
    [
        (OSError("network " + SECRET), "inaccessible"),
        (TimeoutError(SECRET), "inaccessible"),
        (SnapMagicRateLimit(42), "42 s"),
        (RuntimeError("HTTP 401 " + SECRET), "confidentiel"),
    ],
)
def test_partner_failures_never_expose_secret(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    error: Exception,
    expected: str,
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.error = error
    with pytest.raises(DomainError, match=expected) as caught:
        service.search(query())
    assert SECRET not in str(caught.value)
    assert partner.calls == ["search"]
    assert service.catalogue.list_entities(Asset) == []


@pytest.mark.parametrize(
    "records",
    [
        ({"fabricated_http_response": SECRET},),
        (record(filename="legacy.lib"),),
        (record(attribution=SECRET),),
        (record(source_url="https://www.snapeda.com/file?token=secret"),),
        (record(), record()),
        tuple(record(identity=str(i)) for i in range(101)),
    ],
)
def test_invalid_normalized_responses(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    records: tuple[object, ...],
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.records = cast(tuple[SnapMagicRecord, ...], records)
    with pytest.raises(DomainError, match="invalide|format"):
        service.search(query())
    assert service.catalogue.list_entities(Asset) == []


@pytest.mark.parametrize(
    "kind,content,filename",
    [
        (AssetType.SYMBOL, SYMBOL.encode(), "R.kicad_sym"),
        (AssetType.FOOTPRINT, FOOTPRINT.encode(), "R.kicad_mod"),
        (AssetType.MODEL_3D, STEP, "model.step"),
        (AssetType.MODEL_3D, WRL, "model.wrl"),
    ],
)
def test_explicit_import_preserves_metadata_and_is_independent_of_temporary_files(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    tmp_path: Path,
    engine: Engine,
    kind: AssetType,
    content: bytes,
    filename: str,
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.records = (record(kind, filename=filename),)
    partner.content = content
    candidate = service.search(query(kind)).candidates[0]
    asset = service.import_download(service.download(candidate))
    assert asset.file and asset.file.sha256 == hashlib.sha256(content).hexdigest()
    assert asset.file.asset_type is kind and asset.validation_state == "UNCHECKED"
    assert asset.provenance and asset.provenance.mpn == MPN
    assert asset.provenance.redistribution is Redistribution.UNKNOWN
    assert asset.source == candidate.source_url
    assert SqliteCatalogue(engine).get(Asset, asset.id) == asset
    assert isinstance(service.catalogue.store, LocalAssetStore)
    service.provider = None
    partner.content = b""
    destination = tmp_path / "retained"
    service.catalogue.store.retrieve(asset.file, str(destination))
    assert destination.read_bytes() == content
    assert SECRET not in (tmp_path / "config/snapmagic.toml").read_text()
    with engine.connect() as connection:
        raw = connection.scalar(
            text("SELECT provenance_json FROM assets WHERE id = :id"), {"id": asset.id.hex}
        )
        assert SECRET not in raw
    renamed = replace(asset, name="Locally renamed")
    service.catalogue.save(renamed)
    for altered in (
        replace(renamed, provenance=None),
        replace(renamed, origin=AssetOrigin.KICAD_OFFICIAL),
    ):
        with pytest.raises(DomainError, match="immuable"):
            service.catalogue.save(altered)
    assert service.catalogue.require(Asset, asset.id) == renamed


@pytest.mark.parametrize(
    "content", [b"", b"<html>login</html>", b"%PDF-1.4 wrong", b"ISO-10303-21; truncated"]
)
def test_invalid_download_does_not_import(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    content: bytes,
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.records = (record(),)
    partner.content = content
    with pytest.raises(DomainError):
        service.download(service.search(query()).candidates[0])
    assert service.catalogue.list_entities(Asset) == []


def test_wrong_hash_and_revoked_access(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.records = (record(sha256="a" * 64),)
    with pytest.raises(DomainError, match="Hash"):
        service.download(service.search(query()).candidates[0])
    partner.records = (record(),)
    download = service.download(service.search(query()).candidates[0])
    service.configure(ThirdPartyConfiguration(False))
    with pytest.raises(DomainError, match="désactivé"):
        service.import_download(download)
    assert service.catalogue.list_entities(Asset) == []


def archive(*entries: tuple[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as writer:
        for name, content in entries:
            writer.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize(
    "entries,valid",
    [
        ((("sub/STM32F103C8T6.step", STEP), ("readme.txt", b"license")), True),
        ((("../STM32F103C8T6.step", STEP),), False),
        ((("a/STM32F103C8T6.step", STEP), ("b/STM32F103C8T6.step", STEP)), False),
        ((("another.step", STEP),), False),
    ],
)
def test_zip_import_selects_one_safe_member(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    entries: tuple[tuple[str, bytes], ...],
    valid: bool,
) -> None:
    service, partner, _ = setup
    enable(service)
    partner.records = (record(),)
    partner.content = archive(*entries)
    candidate = service.search(query()).candidates[0]
    if valid:
        asset = service.import_download(service.download(candidate))
        assert asset.file and asset.file.sha256 == hashlib.sha256(STEP).hexdigest()
    else:
        with pytest.raises(DomainError, match="Archive"):
            service.download(candidate)
        assert service.catalogue.list_entities(Asset) == []


def test_configuration_and_environment_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SnapMagicSettings(tmp_path)
    assert settings.load() == ThirdPartyConfiguration()
    monkeypatch.setenv("KIPART_SNAPMAGIC_CREDENTIAL", SECRET)
    assert EnvironmentCredential().read() == SECRET
    settings.save(ThirdPartyConfiguration(True))
    assert SECRET not in settings.path.read_text()
    settings.path.write_text('enabled = "yes"')
    with pytest.raises(DomainError, match="illisible"):
        settings.load()
    settings.save(ThirdPartyConfiguration())
    assert not settings.load().enabled


def test_migration_upgrade_and_safe_downgrade(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "migration.sqlite3")
    try:
        migrate(engine, "0006_documentation")
        # Seed with the old schema using SQL, without the newer ORM mapping.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets VALUES ('123', 'Old', 'MODEL_3D', "
                    "'USER_PROVIDED', '', 'UNCHECKED')"
                )
            )
        migrate(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT name FROM assets WHERE id='123'")) == "Old"
            assert (
                connection.scalar(text("SELECT provenance_json FROM assets WHERE id='123'")) is None
            )
        migrate(engine, "0006_documentation", downgrade=True)
        migrate(engine)
        with engine.begin() as connection:
            connection.execute(text("UPDATE assets SET provenance_json='{}' WHERE id='123'"))
        with pytest.raises(RuntimeError, match="would be lost"):
            migrate(engine, "0006_documentation", downgrade=True)
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT provenance_json FROM assets WHERE id='123'")) == "{}"
            )
    finally:
        engine.dispose()


def test_offline_priority_and_normal_validation(
    tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network attempted")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    validation, resolver, part, package, _, _ = setup_case(tmp_path, engine)
    partner, credential = FixturePartner(), FixtureCredential()
    partner.records = (record(),)
    service = ThirdPartyResolver(
        validation.catalogue,
        SnapMagicSettings(tmp_path),
        ThirdPartyInspector(),
        SnapMagicAdapter(credential, partner),
    )
    enable(service)
    before = resolver.choices(package)
    asset = service.import_download(service.download(service.search(query()).candidates[0]))
    assert resolver.choices(package) == before
    current = validation.catalogue.require(Part, part.id)
    assert validation.qualification(current).state == "UNCHECKED"
    chosen = next(
        c for c in resolver.search(package, AssetType.MODEL_3D, "").candidates if c.asset == asset
    )
    resolver.select(package, chosen)
    assert validation.validate(part).level.value == "WARNING"  # STEP envelope only, same M5 policy.
    assert asset.validation_state == "UNCHECKED"
    service.provider = None
    assert resolver.search(package, AssetType.MODEL_3D, "").candidates[0].asset == asset


def test_managed_third_party_publication_and_v1_transport(
    setup: tuple[ThirdPartyResolver, FixturePartner, FixtureCredential],
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.domain.entities import Collection
    from kipartmanager.infrastructure.bundles import LocalBundles
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.publications import LocalPublications
    from tests.test_publisher import local_probe

    service, partner, _ = setup
    footprint = (
        FOOTPRINT[:-1] + '(model "STM32F103C8T6.step" (offset (xyz 0 0 0)) '
        "(scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))"
    )
    validation, resolver, _, package, collection, _ = setup_case(
        tmp_path, engine, footprint=footprint
    )
    enable(service)
    partner.records = (record(),)
    candidate = service.search(query()).candidates[0]
    asset = service.import_download(service.download(candidate))
    resolver.select(package, resolver.search(package, AssetType.MODEL_3D, asset.name).candidates[0])
    assert not validation.validate(collection).eligible
    validation.validate(collection, accept_warnings=True)
    builder = LocalLibraryBuilder(
        local_probe(validation).store, LocalKiCadIndex(tmp_path / "data"), tmp_path / "data"
    )
    history = LocalPublications(tmp_path / "history", builder)
    publications = Publications(LocalPublisher(validation.catalogue, validation, builder), history)
    publication = publications.publish(collection, 1)
    source = LocalBundles(cast(SqliteCatalogue, service.catalogue.repository), history)
    archive = tmp_path / "third-party.kiparts"
    source.export(publication, str(archive))
    service.provider = None

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    # Importing v1 over the source must retain its richer local provenance.
    assert source.import_bundle(str(archive)).can_import
    assert service.catalogue.require(Asset, asset.id).provenance == asset.provenance
    target_engine = create_database_engine(tmp_path / "target/database.sqlite3")
    try:
        migrate(target_engine)
        store = LocalAssetStore(tmp_path / "target/assets")
        target_builder = LocalLibraryBuilder(
            store, LocalKiCadIndex(tmp_path / "target"), tmp_path / "target"
        )
        target_history = LocalPublications(tmp_path / "target/history", target_builder)
        target = LocalBundles(SqliteCatalogue(target_engine), target_history)
        target.import_bundle(str(archive))
        transported = target.repository.get(Asset, asset.id)
        assert transported and transported.file == asset.file
        assert transported.origin is AssetOrigin.TRUSTED_THIRD_PARTY
        assert transported.source == asset.source
        assert transported.provenance is None  # M8 v1 has no rich rights metadata.
        assert target.repository.get(Collection, collection.id)
        Publications(
            LocalPublisher(validation.catalogue, validation, builder), target_history
        ).verify(publication)
    finally:
        target_engine.dispose()
