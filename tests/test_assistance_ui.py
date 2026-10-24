"""Offline Qt consent, review, conflict and optional-provider workflows."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from tests.test_assistance import FixtureAssistant
from tests.test_validation import setup_case

from kipartmanager.application.assistance import Assistance
from kipartmanager.application.documentation import Documentation
from kipartmanager.domain.documentation import (
    FieldValue,
    MetadataField,
    MetadataProposal,
    MetadataSource,
)
from kipartmanager.domain.entities import Part
from kipartmanager.infrastructure.assistance import AssistanceToml
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import LocalProposalReader, SqliteDocumentation
from kipartmanager.ui.main_window import MainWindow


def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected network")


socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.getaddrinfo = forbidden
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
captures = root / "captures"
captures.mkdir(exist_ok=True)
app = QApplication([])
engine = create_database_engine(root / "database.sqlite3")
migrate(engine)
validation, resolver, part, package, collection, assets = setup_case(root, engine)
docs = Documentation(
    validation.catalogue,
    SqliteDocumentation(engine),
    LocalProposalReader(),
    ManufacturerSettings(root),
)
initial = docs.identification(part.id)
docs.accept(
    initial,
    MetadataProposal(
        MetadataSource("User", "user:manual"), (FieldValue(MetadataField.MPN, "USER-MPN"),)
    ),
    (MetadataField.MPN,),
)


class SlowAssistant(FixtureAssistant):
    def suggest(self, request, config):
        time.sleep(0.15)
        return super().suggest(request, config)


provider = SlowAssistant()
service = Assistance(AssistanceToml(root), provider)
window = MainWindow(validation.catalogue, resolver=resolver, documentation=docs, assistance=service)
window.show()
window.open_documentation(part)
doc = window.documentation_panel
panel = doc.assistance_panel
assert panel is not None


def capture(name):
    app.processEvents()
    window.grab().save(str(captures / (name + ".png")))


def wait_worker():
    deadline = time.monotonic() + 5
    while panel.worker is not None:
        app.processEvents()
        time.sleep(0.005)
        assert time.monotonic() < deadline
    app.processEvents()


def prepare():
    doc.tabs.setCurrentWidget(panel)
    panel.include_values.setChecked(False)
    panel.context.setPlainText("R123, résistance de précision. Ne déduire aucune valeur inconnue.")
    panel.prepare()
    assert panel.request
    assert "USER-MPN" not in panel.payload.toPlainText()
    assert not panel.send_button.isEnabled()
    panel.consent.setChecked(True)
    assert panel.send_button.isEnabled()


# Disabled, configuration and secret-independent fake are explicit.
doc.tabs.setCurrentWidget(panel)
capture("disabled")
panel.context.setPlainText("Test")
panel.prepare()
assert "Activer" in panel.message.text() and provider.calls == 0
panel.config_toggle.setChecked(True)
panel.gemini()
panel.model.setText("fixture-gemini")
panel.enabled.setChecked(True)
panel.configure()
capture("config-gemini")
assert provider.calls == 0
panel.config_toggle.setChecked(False)
prepare()
panel.include_values.setChecked(True)
assert not panel.send_button.isEnabled() and not panel.consent.isChecked()
panel.prepare()
assert "USER-MPN" in panel.payload.toPlainText()
panel.consent.setChecked(True)
capture("consent-preview")
before = docs.identification(part.id)
panel.send()
assert panel.worker and not doc.parts.isEnabled()
assert not window.close()
capture("searching")
wait_worker()
assert docs.identification(part.id) == before
assert doc.tabs.currentIndex() == 0
assert doc.proposal.source.origin.value == "GENERATED_AI"
assert all(
    doc.comparison.item(row, 0).checkState() == Qt.CheckState.Unchecked
    for row in range(doc.comparison.rowCount())
)
capture("review")
# Ignoring leaves both values and history intact.
doc.load_part()
assert docs.identification(part.id) == before
prepare()
panel.send()
wait_worker()
for row in range(doc.comparison.rowCount()):
    item = doc.comparison.item(row, 0)
    if item.data(Qt.ItemDataRole.UserRole) == "category":
        item.setCheckState(Qt.CheckState.Checked)
doc.accept_proposal()
assert docs.identification(part.id).value(MetadataField.MPN) == "USER-MPN"
assert docs.identification(part.id).value(MetadataField.CATEGORY) == "Resistor"
assert docs.identification(part.id).history[-1].source.origin.value == "GENERATED_AI"
doc.history.show()
capture("accepted-history")
# Failure, absent provider and concurrent identification stay non-destructive.
provider.error = OSError("fixture private error")
prepare()
panel.send()
wait_worker()
assert "indisponible" in panel.message.text()
capture("provider-error")
service.provider = None
prepare()
panel.send()
wait_worker()
assert "non configuré" in panel.message.text()
capture("provider-absent")
service.provider = provider
provider.error = None
prepare()
panel.send()
current = docs.identification(part.id)
docs.accept(
    current,
    MetadataProposal(
        MetadataSource("Concurrent", "user:concurrent"),
        (FieldValue(MetadataField.NOTES, "Keep this edit"),),
    ),
    (MetadataField.NOTES,),
)
wait_worker()
assert "modifiée" in panel.message.text()
assert docs.identification(part.id).value(MetadataField.NOTES) == "Keep this edit"
panel.ollama()
panel.model.setText("fixture-local")
panel.configure()
prepare()
for name, size in [("narrow", (900, 680)), ("normal", (1200, 800)), ("wide", (1600, 950))]:
    window.resize(*size)
    capture("preview-" + name)
other = Part(name="Another part")
validation.catalogue.save(other)
window.open_documentation(other)
assert not panel.request and not panel.consent.isChecked() and not panel.context.toPlainText()
assert window.close()
engine.dispose()
print(
    "M11 native/offline: consent, Gemini/Ollama configuration, "
    "review/reject/accept, history, stale/errors and three sizes PASS"
)
print(captures)
"""


def test_assistance_ui_offline(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
