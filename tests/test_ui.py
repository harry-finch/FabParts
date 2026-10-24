"""Exercise create/edit forms and reopen persistence without GUI automation tooling."""

import os
import subprocess
import sys
from pathlib import Path


def test_ui_create_edit_and_reopen(tmp_path: Path) -> None:
    script = """
import socket
import sys
from pathlib import Path
from dataclasses import replace

def forbidden(*args, **kwargs):
    raise AssertionError('Network access attempted')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from PySide6.QtCore import Qt
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import *
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.entity_dialog import EntityDialog

app = QApplication([])
engine = create_database_engine(Path(sys.argv[1]) / 'catalogue.sqlite3')
migrate(engine)
service = Catalogue(SqliteCatalogue(engine))
service.initialize_defaults()
window = MainWindow(service)
window.show()
app.processEvents()
assert window.tabs.count() == 4

def submit(dialog):
    dialog.show()
    app.processEvents()
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
    button.click()
    app.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    window.refresh()

records = []
for kind in (Asset, Package, Part, Inventory, Location, Collection):
    dialog = EntityDialog(service, kind, parent=window)
    dialog.name.setText('Created ' + kind.__name__)
    if kind is Part:
        dialog.combos['package'].setCurrentIndex(1)
        dialog.members.item(0).setCheckState(Qt.CheckState.Checked)
    if kind is Collection:
        dialog.members.item(0).setCheckState(Qt.CheckState.Checked)
    submit(dialog)
    entity = next(item for item in service.list_entities(kind)
                  if item.name == 'Created ' + kind.__name__)
    edit = EntityDialog(service, kind, entity, window)
    edit.name.setText('Edited ' + kind.__name__)
    if kind is Asset:
        edit.source.setText('source retained')
    if kind is Part:
        assert edit.combos['package'].currentData() == str(entity.package_id)
        assert edit.members.item(0).checkState() == Qt.CheckState.Checked
        edit.combos['state'].setCurrentText('IDENTIFIED')
    submit(edit)
    records.append(service.require(kind, entity.id))

stock_dialog = EntityDialog(service, StockItem, parent=window)
stock_dialog.quantity.setText('4294967296')
stock_dialog.combos['location'].setCurrentIndex(1)
submit(stock_dialog)
stock = service.list_entities(StockItem)[0]
edit = EntityDialog(service, StockItem, stock, window)
assert edit.quantity.text() == '4294967296'
edit.quantity.setText('0')
submit(edit)
records.append(service.require(StockItem, stock.id))

invalid_quantity = EntityDialog(service, StockItem, stock, window)
invalid_quantity.quantity.setText('1.5')
invalid_quantity.save()
assert invalid_quantity.error.text()
assert service.require(StockItem, stock.id).quantity == 0
invalid_quantity.close()

# Validation failure keeps the dialog open and the stored record unchanged.
invalid = EntityDialog(service, Inventory, parent=window)
invalid.name.setText('Lab')
invalid.save()
assert invalid.result() != QDialog.DialogCode.Accepted
assert invalid.error.text()
invalid.close()
window.close()
engine.dispose()
reopened = create_database_engine(Path(sys.argv[1]) / 'catalogue.sqlite3')
migrate(reopened)
again = Catalogue(SqliteCatalogue(reopened))
again.initialize_defaults()
for record in records:
    assert again.require(type(record), record.id) == record
assert again.list_entities(StockItem)[0].quantity == 0
reopened.dispose()
print('Seven UI entity editors, modifications, associations and reopen: PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
