"""Offline Qt configuration, threaded rebuild, search and restart."""

import os
import subprocess
import sys
from pathlib import Path


def test_kicad_offline_ui(tmp_path: Path) -> None:
    script = """
import socket
import sys
import time
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError("Network access attempted")
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden

from PySide6.QtWidgets import QApplication
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.ui.main_window import MainWindow

root = Path(sys.argv[1])
symbols = root / "official/symbols"
symbols.mkdir(parents=True)
source = symbols / "Timer.kicad_sym"
source.write_text('(kicad_symbol_lib (version 20251024) (generator fixture) '
                  '(symbol "NE555" (property "Description" "Timer")))')
before = source.read_bytes()
app = QApplication([])
engine = create_database_engine(root / "data/database/catalogue.sqlite3")
migrate(engine)
service = KiCadLibraries(LocalKiCadIndex(root / "data"))
window = MainWindow(Catalogue(SqliteCatalogue(engine)), libraries=service)
window.show()
panel = window.kicad_panel
assert window.tabs.count() == 5
assert panel is not None
assert panel.issues.count() == 1
panel.paths[0].setText(str(symbols))
panel.save_button.click()
panel.rebuild_button.click()
assert panel.worker is not None
assert not panel.save_button.isEnabled()
window.close()
assert window.isVisible()  # Closing is prevented while the worker is active.
deadline = time.monotonic() + 10
while panel.worker is not None and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.01)
assert panel.worker is None
assert panel.save_button.isEnabled()
assert "1 références" in panel.status.text()
panel.query.setText("ne555")
panel.search()
assert panel.items.count() == 1
assert panel.references[0].identifier == "Timer:NE555"
assert "Official KiCad" in panel.items.item(0).text()
assert "UNCHECKED" in panel.items.item(0).text()
panel.paths[0].setText(str(root / "missing"))
panel.rebuild_button.click()
assert "absent" in panel.status.text()
assert len(service.search("NE555")) == 1
window.close()
app.processEvents()
reopened = MainWindow(Catalogue(SqliteCatalogue(engine)), libraries=service)
reopened.show()
assert reopened.kicad_panel.paths[0].text() == str(symbols.resolve())
reopened.kicad_panel.query.setText("Timer")
reopened.kicad_panel.search()
assert reopened.kicad_panel.items.count() == 1
assert source.read_bytes() == before
assert not (root / "data/assets").exists()
reopened.close()
app.processEvents()
engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
