"""Native-capable M10.5 integration with a normalized fixture and forbidden sockets."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket, sys, time
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.third_party_assets import ThirdPartyResolver
from kipartmanager.domain.documentation import (
    MetadataSource,
    MetadataProposal,
    FieldValue,
    MetadataField,
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Part
from kipartmanager.domain.third_party_assets import ThirdPartyConfiguration
from kipartmanager.infrastructure.snapmagic import (
    SnapMagicSettings,
    ThirdPartyInspector,
    SnapMagicAdapter,
)
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import SqliteDocumentation, LocalProposalReader
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.ui.main_window import MainWindow
from tests.test_snapmagic import FixturePartner, FixtureCredential, record, STEP, MPN
from tests.test_validation import setup_case


def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden")


socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
captures = root / "captures"
captures.mkdir(exist_ok=True)
app = QApplication([])
engine = create_database_engine(root / "database.sqlite3")
migrate(engine)
validation, resolver, part, package, collection, assets = setup_case(root, engine)
catalogue = validation.catalogue
imports = AssetImports(catalogue, catalogue.store)
original = imports.import_content(
    STEP + b"\nuser model",
    "original.step",
    name="User model",
    origin=AssetOrigin.USER_PROVIDED,
    source_reference="fixture:user",
)
resolver.select(
    package,
    next(
        c
        for c in resolver.search(package, AssetType.MODEL_3D, "").candidates
        if c.asset == original
    ),
)
choices = resolver.choices(package)
docs = Documentation(
    catalogue, SqliteDocumentation(engine), LocalProposalReader(), ManufacturerSettings(root)
)
docs.accept(
    docs.identification(part.id),
    MetadataProposal(
        MetadataSource("User", "user:local"),
        (
            FieldValue(MetadataField.MPN, MPN),
            FieldValue(MetadataField.MANUFACTURER, "STMicroelectronics"),
        ),
    ),
    (MetadataField.MPN, MetadataField.MANUFACTURER),
)


class SlowPartner(FixturePartner):
    def search(self, query, credential):
        time.sleep(0.18)
        return super().search(query, credential)

    def download(self, candidate, credential):
        time.sleep(0.18)
        return super().download(candidate, credential)


partner = SlowPartner()
credential = FixtureCredential()
partner.records = (
    record(),
    record(identity="second", filename="other.step", name=MPN + " alternative"),
)
service = ThirdPartyResolver(
    catalogue, SnapMagicSettings(root), ThirdPartyInspector(), SnapMagicAdapter(credential, partner)
)
window = MainWindow(
    catalogue,
    imports,
    resolver=resolver,
    validation=validation,
    documentation=docs,
    third_party=service,
)
window.show()
dialog = window.resource_dialog(part, window)
dialog.role.setCurrentIndex(dialog.role.findData(AssetType.MODEL_3D.value))
dialog.show()
panel = dialog.snapmagic
assert panel is not None
assert panel.mpn.text() == MPN and panel.manufacturer.text() == "STMicroelectronics"
dialog.provider_tabs.setCurrentIndex(1)


def pump():
    loop = QEventLoop()
    QTimer.singleShot(25, loop.quit)
    loop.exec()


def capture(name):
    pump()
    dialog.grab().save(str(captures / (name + ".png")))


def wait_worker():
    deadline = time.monotonic() + 5
    while panel.worker is not None and time.monotonic() < deadline:
        pump()
    assert panel.worker is None


capture("disabled")
panel.search_button.click()
assert partner.calls == [] and "désactivé" in panel.message.text()
panel.enabled.setChecked(True)
panel.save_button.click()
credential.value = None
panel.refresh_state()
capture("not-configured")
panel.search_button.click()
assert partner.calls == [] and "non configuré" in panel.message.text()
credential.value = "fixture-secret-never-persisted"
service.provider = SnapMagicAdapter(credential)
panel.refresh_state()
capture("contract-required")
panel.search_button.click()
assert partner.calls == [] and "Contrat API" in panel.message.text()
service.provider = SnapMagicAdapter(credential, partner)
panel.refresh_state()
panel.search_button.click()
assert panel.worker is not None and not dialog.role.isEnabled()
capture("searching")
assert not dialog.close()
dialog.reject()
dialog.accept()
assert dialog.isVisible()
wait_worker()
assert len(panel.candidates) == 2
assert len(catalogue.list_entities(Asset)) == 3
panel.items.setCurrentRow(0)
for name, size in [("normal", (1000, 800)), ("narrow", (820, 680)), ("wide", (1400, 950))]:
    dialog.resize(*size)
    capture("result-" + name)
assert (
    "unknown" in panel.details.toPlainText()
    and "TRUSTED_THIRD_PARTY" in panel.details.toPlainText()
)
panel.import_button.click()
wait_worker()
assert len(catalogue.list_entities(Asset)) == 4
imported = next(a for a in catalogue.list_entities(Asset) if a.provenance)
assert imported.validation_state == "UNCHECKED" and imported.file
assert imported.provenance.provider == "SnapMagic / SnapEDA"
assert resolver.choices(package) == choices
capture("import-success")
# New managed candidate follows the selected user resource. Explicit replacement remains required.
dialog.provider_tabs.setCurrentIndex(0)
row = next(i for i, c in enumerate(dialog.candidates) if c.asset == imported)
dialog.items.setCurrentRow(row)
dialog.select_button.click()
assert "Confirmer" in dialog.message.text() and resolver.choices(package) == choices
dialog.confirm_replace.setChecked(True)
dialog.select_button.click()
assert any(c.asset_id == imported.id for c in resolver.choices(package))
assert validation.validate(catalogue.require(Part, part.id)).level.value == "WARNING"
capture("selected-local")
# Changing search context clears remote candidates and their import action.
dialog.provider_tabs.setCurrentIndex(1)
panel.mpn.setText("NO-MATCH")
partner.records = ()
panel.search_button.click()
wait_worker()
assert not panel.candidates and not panel.import_button.isEnabled()
capture("no-result")
panel.mpn.setText(MPN)
partner.error = OSError("offline secret must stay hidden")
panel.search_button.click()
wait_worker()
assert "inaccessible" in panel.message.text() and len(catalogue.list_entities(Asset)) == 4
capture("offline-error")
service.provider = None
panel.refresh_state()
panel.search_button.click()
assert "non configuré" in panel.message.text()
capture("provider-absent")
service.configure(ThirdPartyConfiguration(False))
assert resolver.search(package, AssetType.MODEL_3D, "").candidates
assert dialog.close()
assert window.close()
app.processEvents()
engine.dispose()
print(
    "M10.5 native/offline: states, exact MPN, candidates, import, "
    "explicit choice, qualification and three sizes PASS"
)
print(captures)

"""


def test_snapmagic_workflow_offline(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
