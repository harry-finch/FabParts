"""M2 import dialog and actions, with offline Qt on disposable data."""

import os
import subprocess
import sys
from pathlib import Path


def test_asset_ui_import_attach_verify_retrieve(tmp_path: Path) -> None:
    script = """
import socket
import sys
from pathlib import Path
def forbidden(*args, **kwargs):
    raise AssertionError('Network access attempted')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
from PySide6.QtWidgets import QApplication, QFileDialog, QDialog, QDialogButtonBox
from PySide6.QtCore import QTimer
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.domain.entities import Asset, AssetType, AssetOrigin
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.entity_dialog import EntityDialog
from kipartmanager.ui.asset_actions import ImportDialog
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
app = QApplication([])
engine = create_database_engine(root / 'database' / 'catalogue.sqlite3')
migrate(engine)
store = LocalAssetStore(root / 'assets')
catalogue = Catalogue(SqliteCatalogue(engine), store)
catalogue.initialize_defaults()
imports = AssetImports(catalogue, store)
window = MainWindow(catalogue, imports)
window.show()
panel = window.panels[2]
window.tabs.setCurrentIndex(2)
app.processEvents()

def accept_import():
    dialog = app.activeModalWidget()
    assert isinstance(dialog, ImportDialog)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()

for extension in ('.pdf', '.step', '.wrl', '.kicad_mod', '.kicad_sym'):
    source = root / ('sample' + extension)
    source.write_bytes(('opaque M2 bytes ' + extension).encode())
    QFileDialog.getOpenFileName = lambda *args, **kwargs: (str(source), '')
    QTimer.singleShot(100, accept_import)
    panel.file_action('import')
    asset = next(item for item in catalogue.list_entities(Asset)
                 if item.name == source.name)
    panel.items.setCurrentRow(next(index for index, value in enumerate(panel.entities)
                                  if value.id == asset.id))
    panel.file_action('verify')
    assert 'vérifiée' in panel.message.text()
    destination = root / ('copy' + extension)
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(destination), '')
    panel.file_action('retrieve')
    assert destination.read_bytes() == source.read_bytes()
    edit = EntityDialog(catalogue, Asset, asset, window)
    edit.name.setText('Edited ' + source.name)
    edit.save()
    assert edit.result() == QDialog.DialogCode.Accepted
    assert catalogue.require(Asset, asset.id).file == asset.file

metadata = Asset(name='M1 metadata', asset_type=AssetType.DATASHEET,
                 origin=AssetOrigin.USER_PROVIDED, source='retained provenance')
catalogue.save(metadata)
window.refresh()
panel.items.setCurrentRow(next(index for index, value in enumerate(panel.entities)
                              if value.id == metadata.id))
source = root / 'sample.pdf'
QFileDialog.getOpenFileName = lambda *args, **kwargs: (str(source), '')
panel.file_action('attach')
attached = catalogue.require(Asset, metadata.id)
assert attached.file is not None and attached.source == 'retained provenance'
panel.items.setCurrentRow(next(index for index, value in enumerate(panel.entities)
                              if value.id == metadata.id))
panel.file_action('attach')
assert 'déjà' in panel.message.text()
destination = root / 'existing.pdf'
destination.write_bytes(b'user file')
QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(destination), '')
panel.file_action('retrieve')
assert destination.read_bytes() == b'user file'
assert 'existe' in panel.message.text()
window.close()
engine.dispose()
print('M2 GUI import/attach/integrity/retrieve and preservation: PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
