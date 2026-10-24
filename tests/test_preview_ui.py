"""Offline inspection actions, zoom, PDF pages and failure states in real Qt."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket
import sys
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.previews import Previews
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Part
from kipartmanager.domain.kicad import LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.preview_reader import LocalPreviewReader
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.preview_dialog import PreviewDialog
from tests.test_previews import SYMBOL, FOOTPRINT

def forbidden(*args, **kwargs):
    raise AssertionError('Network used during local preview')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
app = QApplication([])
engine = create_database_engine(root / 'db.sqlite3'); migrate(engine)
repository = SqliteCatalogue(engine)
store = LocalAssetStore(root / 'assets')
catalogue = Catalogue(repository, store); catalogue.initialize_defaults()
imports = AssetImports(catalogue, store)
symbol = imports.import_content(SYMBOL.encode(), 'fixture.kicad_sym', name='Child',
    origin=AssetOrigin.USER_PROVIDED, source_reference='fixture')
footprint = imports.import_content(FOOTPRINT.encode(), 'fixture.kicad_mod', name='SOIC',
    origin=AssetOrigin.USER_PROVIDED, source_reference='fixture')
index = LocalKiCadIndex(root / 'index')
official_dir = root / 'official'; official_dir.mkdir()
(official_dir / 'Fixture.kicad_sym').write_text(SYMBOL)
index.configure(LibraryRoots(symbols=str(official_dir))); index.rebuild(index.configuration())
service = Previews(catalogue, LocalPreviewReader(store, index))
resolver = LocalResolver(catalogue, repository, KiCadLibraries(index))
part = Part(name='Child', asset_ids=(symbol.id,)); catalogue.save(part)
resolver.select(part, resolver.search(part, AssetType.SYMBOL, symbol.name).candidates[0])
window = MainWindow(catalogue, imports, KiCadLibraries(index), resolver, previews=service)
window.show()

def pump():
    loop = QEventLoop(); QTimer.singleShot(50, loop.quit); loop.exec()

window.inspect_resource(ResourceChoice(AssetType.SYMBOL, asset_id=symbol.id))
pump()
dialog = window.findChildren(PreviewDialog)[-1]
assert dialog.isVisible() and not dialog.isModal()
assert dialog.entries.count() == 4
assert dialog.drawing_view.canvas.items()
dialog.entries.setCurrentIndex(3)
texts = {item.text() for item in dialog.drawing_view.canvas.items() if hasattr(item, 'text')}
assert texts == {'OUT','2'}
scale = dialog.drawing_view.transform().m11()
dialog.plus.click(); assert dialog.drawing_view.transform().m11() > scale
dialog.fit_button.click()
for w,h in [(900,680),(1200,800),(1600,950)]:
    dialog.resize(w,h); pump()
    assert dialog.drawing_view.width() > 300
    assert dialog.drawing_view.height() > 150
    dialog.grab().save(str(root/f'symbol-{w}.png'))
assert catalogue.require(Asset,symbol.id) == symbol
assert resolver.choices(part)[0].asset_id == symbol.id
dialog.close(); pump()
component_row = next(i for i,p in enumerate(window.components_panel.entities) if p.id==part.id)
window.components_panel.table.selectRow(component_row)
window.components_panel.show_details()
row=window.components_panel.resource_rows[AssetType.SYMBOL]
assert row.inspect.isEnabled()
row.inspect.click(); pump(); window.findChildren(PreviewDialog)[-1].close(); pump()
asset_panel=window.entity_panels[Asset]
asset_row = next(i for i,a in enumerate(asset_panel.entities) if a.id==footprint.id)
asset_panel.items.setCurrentRow(asset_row)
asset_panel.preview_button.click(); pump()
dialog=window.findChildren(PreviewDialog)[-1]
assert any(p.layer=='Pad1' for p in dialog.drawings[0].primitives)
dialog.grab().save(str(root/'footprint.png')); dialog.close(); pump()
kicad=window.kicad_panel
kicad.query.setText('Child'); kicad.search(); kicad.items.setCurrentRow(0)
assert kicad.preview_button.isEnabled()
kicad.preview_button.click(); pump()
dialog=window.findChildren(PreviewDialog)[-1]
assert dialog.entries.count()==2
assert 'Official KiCad' in dialog.source.toPlainText()
dialog.close(); pump()
resource_dialog=window.resource_dialog(part,window)
resource_dialog.items.setCurrentRow(0)
assert resource_dialog.preview_button.isEnabled()
resource_dialog.preview_button.click(); pump()
assert resource_dialog.findChildren(PreviewDialog)[-1].isVisible()
resource_dialog.findChildren(PreviewDialog)[-1].close(); pump(); resource_dialog.close()
# Generate a valid two-page PDF with Qt, avoiding external fixture dependencies.
filename=root/'two-pages.pdf'
writer=QPdfWriter(str(filename))
painter=QPainter(writer); painter.drawText(100,100,'Page one'); writer.newPage()
painter.drawText(100,100,'Page two'); painter.end(); del writer
pdf=imports.import_file(str(filename))
dialog=PreviewDialog(service,ResourceChoice(AssetType.DATASHEET,asset_id=pdf.id),window)
dialog.show(); pump()
assert dialog.document.status()==QPdfDocument.Status.Ready
assert dialog.page.maximum()==2 and dialog.page.isEnabled()
dialog.page.setValue(2); pump()
assert dialog.pdf_view.pageNavigator().currentPage()==1
dialog.plus.click(); assert dialog.pdf_view.zoomFactor()>0
dialog.grab().save(str(root/'pdf.png')); dialog.close(); pump()
bad=imports.import_content(b'%PDF-1.7\ninvalid','bad.pdf', name='Bad PDF',
    origin=AssetOrigin.USER_PROVIDED, source_reference='fixture')
dialog=PreviewDialog(service,ResourceChoice(AssetType.DATASHEET,asset_id=bad.id),window)
dialog.show(); pump()
assert dialog.document.status()==QPdfDocument.Status.Error
assert 'PDF illisible' in dialog.message.text() and not dialog.plus.isEnabled()
dialog.close(); pump()
assert symbol.file is not None
(store.root/symbol.file.relative_key).write_bytes(b'changed')
dialog=PreviewDialog(service,ResourceChoice(AssetType.SYMBOL,asset_id=symbol.id),window)
dialog.show(); pump()
assert 'corrompu' in dialog.message.text() and not dialog.plus.isEnabled()
dialog.grab().save(str(root/'error.png')); dialog.close(); window.close(); pump()
engine.dispose()
print('Preview UI: offline, actions, sizes, units, zoom, PDF and errors OK')
"""


def test_previews_offline_ui(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
