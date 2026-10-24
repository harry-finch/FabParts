"""Remote worker lifecycle and opt-in Qt workflow with actual network forbidden."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Part
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.remote_kicad import OfficialGitLab, TomlRemoteSettings
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.resolver_dialog import ResolverDialog
from tests.test_remote_kicad import FixtureHTTP, SYMBOL

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
captures = root / 'captures'
captures.mkdir(exist_ok=True)

def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected network')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
app = QApplication([])
engine = create_database_engine(root / 'database.sqlite3')
migrate(engine)
repo = SqliteCatalogue(engine)
store = LocalAssetStore(root / 'assets')
catalogue = Catalogue(repo, store)
catalogue.initialize_defaults()
imports = AssetImports(catalogue, store)
user = imports.import_content(SYMBOL, 'user.kicad_sym', name='R_Small',
    origin=AssetOrigin.USER_PROVIDED,
    source_reference='user')
part = Part(name='R_Small', asset_ids=(user.id,))
catalogue.save(part)
local = LocalResolver(catalogue, repo, KiCadLibraries(LocalKiCadIndex(root)))
local.select(part, local.search(part, AssetType.SYMBOL, 'R_Small').candidates[0])
http = FixtureHTTP()
remote = RemoteLibraries(TomlRemoteSettings(root), imports, OfficialGitLab(http))
window = MainWindow(catalogue, imports, local.libraries, local, remote_libraries=remote)
window.show()
window.open_remote()
panel = window.remote_panel
assert panel is not None and not panel.enabled.isChecked()
assert http.calls == []

def pump():
    loop = QEventLoop()
    QTimer.singleShot(35, loop.quit)
    loop.exec()

def wait_worker():
    deadline=time.monotonic()+5
    while panel.worker is not None and time.monotonic() < deadline:
        pump()
    assert panel.worker is None

def capture(name):
    pump()
    window.grab().save(str(captures / (name+'.png')))

capture('disabled')
panel.library.setText('Device')
panel.search_button.click()
assert 'désactivée' in panel.message.text() and http.calls == []
panel.enabled.setChecked(True)
panel.search_button.click()
assert 'Enregistrer' in panel.message.text() and http.calls == []
panel.save_button.click()
panel.query.setText('R_Small')
panel.search_button.click()
assert not panel.search_button.isEnabled()
assert not window.close() # In-flight worker keeps window alive.
wait_worker()
assert panel.items.count()==1 and catalogue.list_entities(Asset)==[user]
assert not panel.import_button.isEnabled()
panel.items.setCurrentRow(0)
assert panel.import_button.isEnabled()
for name,size in [('normal',(1200,800)),('narrow',(900,680)),('wide',(1600,950))]:
    window.resize(*size)
    capture('selected-'+name)
panel.import_button.click()
wait_worker()
assert 'importé' in panel.message.text()
assert len(catalogue.list_entities(Asset))==2
assert local.choices(part)[0].asset_id==user.id
capture('success')
window.components_panel.refresh()
http.failure='Réseau indisponible'
panel.search_button.click()
wait_worker()
assert 'Réseau' in panel.message.text()
assert panel.items.count()==0 and not panel.import_button.isEnabled()
capture('failure')
# Local path still works with configured but failed remote adapter.
dialog=ResolverDialog(local,part,window,remote_open=window.open_remote)
dialog.show()
assert len(dialog.candidates)==2 and dialog.candidates[0].asset.id==user.id
assert dialog.expected.asset_id==user.id
assert dialog.candidates[1].asset.file.symbol_name=='R_Small'
dialog.items.setCurrentRow(1)
dialog.select_button.click()
assert 'Confirmer' in dialog.message.text()
assert local.choices(part)[0].asset_id==user.id
dialog.confirm_replace.setChecked(True)
dialog.select_button.click()
assert local.choices(part)[0].asset_id!=user.id
dialog.remote_button.click()
assert window.kicad_workspace.currentWidget() is panel
panel.enabled.setChecked(False)
panel.save_button.click()
assert not remote.configuration().enabled
remote.provider=None
panel.enabled.setChecked(True)
panel.save_button.click()
panel.search_button.click()
assert 'absent' in panel.message.text()
capture('absent')
assert catalogue.require(Asset,user.id)==user
window.close()
app.processEvents()
engine.dispose()
print('M9 UI offline, opt-in, search, download, explicit replacement, '
      'failure, absent adapter and three sizes PASS')
print(captures)
"""


def test_remote_offline_ui(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
