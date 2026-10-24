"""Offline Qt comparison, explicit replacement, shared package and restart."""

import os
import subprocess
import sys
from pathlib import Path


def test_resolver_offline_ui(tmp_path: Path) -> None:
    script = """
import socket
import sys
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError("Network access attempted")
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Package, Part
from kipartmanager.domain.kicad import LibraryRoots
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.resolver_dialog import ResolverDialog

root = Path(sys.argv[1]).resolve()
app = QApplication([])
engine = create_database_engine(root / "data/database/catalogue.sqlite3")
migrate(engine)
repository = SqliteCatalogue(engine)
store = LocalAssetStore(root / "data/assets")
catalogue = Catalogue(repository, store)
source = root / "R.kicad_sym"
source.write_text('(kicad_symbol_lib (version 20251024) (generator fixture) (symbol "R"))')
imports = AssetImports(catalogue, store)
user = imports.import_file(str(source), name="R", source_reference="user")
managed = imports.import_file(str(source), name="R", origin=AssetOrigin.MANAGED_LIBRARY)
footprint_source = root / "R.kicad_mod"
footprint_source.write_bytes(b"opaque footprint M2")
footprint = imports.import_file(str(footprint_source), name="R package footprint")
symbols = root / "official/symbols"
symbols.mkdir(parents=True)
official_file = symbols / "Device.kicad_sym"
official_file.write_bytes(source.read_bytes())
before = official_file.read_bytes()
index = LocalKiCadIndex(root / "data")
index.configure(LibraryRoots(symbols=str(symbols)))
index.rebuild(index.configuration())
libraries = KiCadLibraries(index)
resolver = LocalResolver(catalogue, repository, libraries)
package = Package(name="R package")
catalogue.save(package)
part = Part(name="R", package_id=package.id, asset_ids=(user.id,))
catalogue.save(part)
catalogue.save(Part(name="R second", package_id=package.id))
window = MainWindow(catalogue, imports, libraries, resolver)
window.show()
window.components_panel.table.selectRow(0)
verified = []
def drive_dialog():
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, ResolverDialog)
    assert dialog.items.count() == 3
    assert dialog.items.currentRow() == -1
    assert [c.origin for c in dialog.candidates] == [
        "USER_PROVIDED", "MANAGED_LIBRARY", "KICAD_OFFICIAL"
    ]
    assert resolver.choices(part) == ()
    dialog.items.setCurrentRow(0)
    dialog.select_button.click()
    assert resolver.choices(part)[0].asset_id == user.id
    dialog.items.setCurrentRow(2)
    dialog.select_button.click()
    assert "Confirmer" in dialog.message.text()
    assert resolver.choices(part)[0].asset_id == user.id
    dialog.confirm_replace.setChecked(True)
    dialog.select_button.click()
    assert resolver.choices(part)[0].reference.identifier == "Device:R"
    assert not dialog.confirm_replace.isChecked()
    dialog.role.setCurrentText("FOOTPRINT")
    assert "package partagé" in dialog.current.text()
    assert dialog.items.count() == 1
    dialog.items.setCurrentRow(0)
    dialog.select_button.click()
    assert resolver.choices(package)[0].asset_id == footprint.id
    dialog.role.setCurrentText("DATASHEET")
    dialog.query.setText("unknown")
    dialog.search_button.click()
    assert "Aucun candidat" in dialog.message.text()
    verified.append(True)
    dialog.accept()
QTimer.singleShot(50, drive_dialog)
window.panels[0].resolve()
assert verified == [True]
assert catalogue.require(Part,part.id).asset_ids == (user.id,)
assert catalogue.require(Package,package.id).asset_ids == (footprint.id,)
assert catalogue.require(Asset,user.id) == user
assert len(catalogue.list_entities(Asset)) == 3
assert official_file.read_bytes() == before
window.close()
app.processEvents()
engine.dispose()
index.cache.unlink()
engine = create_database_engine(root / "data/database/catalogue.sqlite3")
migrate(engine)
repository = SqliteCatalogue(engine)
catalogue = Catalogue(repository,store)
resolver = LocalResolver(catalogue,repository,libraries)
reopened = MainWindow(catalogue, resolver=resolver)
reopened.show()
dialog = ResolverDialog(resolver, catalogue.require(Part,part.id), reopened)
dialog.show()
assert "Device:R" in dialog.current.text()
assert "kicad:SYMBOL:" not in dialog.current.text()
assert dialog.items.count() == 2
assert dialog.notices.count() > 0
assert resolver.choices(part)[0].reference.identifier == "Device:R"
dialog.close()
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
