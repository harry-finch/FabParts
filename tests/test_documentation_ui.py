"""M10 Qt enrichment and document workflows with actual sockets blocked."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket
import sys
import time
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QFileDialog
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.datasheets import DatasheetConfiguration
from kipartmanager.domain.documentation import (
    MetadataField, MetadataSource, FieldValue, MetadataProposal
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, Part
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import SqliteDocumentation, LocalProposalReader
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.resolver_dialog import ResolverDialog
from tests.test_documentation import FixtureManufacturer, PDF

def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected network')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
captures = root / 'captures'
captures.mkdir(exist_ok=True)
app = QApplication([])
engine = create_database_engine(root / 'database.sqlite3')
migrate(engine)
repository = SqliteCatalogue(engine)
store = LocalAssetStore(root / 'assets')
catalogue = Catalogue(repository, store)
catalogue.initialize_defaults()
part = Part(name='R-123', description='User description retained')
other = Part(name='Other')
catalogue.save(part)
catalogue.save(other)
imports = AssetImports(catalogue, store)
original = imports.import_content(PDF, 'original.pdf', name='Original',
    origin=AssetOrigin.USER_PROVIDED, source_reference='user:original')
resolver = LocalResolver(catalogue, repository)
resolver.select(part, resolver.search(part, AssetType.DATASHEET, 'Original').candidates[0])
provider = FixtureManufacturer()
service = Documentation(catalogue, SqliteDocumentation(engine), LocalProposalReader(),
    ManufacturerSettings(root), provider)
window = MainWindow(catalogue, imports, resolver=resolver, documentation=service)
window.show()
window.open_documentation(part)
panel = window.documentation_panel
assert panel is not None
assert window.navigation.count()==4 # Optional KiCad/Publications services omitted.

def pump():
    loop = QEventLoop()
    QTimer.singleShot(35, loop.quit)
    loop.exec()

def capture(name):
    pump()
    window.grab().save(str(captures/(name+'.png')))

def wait_worker():
    deadline = time.monotonic()+5
    while panel.worker is not None and time.monotonic()<deadline:
        pump()
    assert panel.worker is None

capture('empty-identification')
panel.fields[MetadataField.MANUFACTURER].setText('User Maker')
panel.preview_button.click()
assert service.identification(part.id).revision==0
panel.accept_button.click()
assert service.identification(part.id).value(MetadataField.MANUFACTURER)=='User Maker'
proposed = MetadataProposal(MetadataSource('Declared manufacturer', 'document:R123',
    AssetOrigin.MANUFACTURER), (FieldValue(MetadataField.MANUFACTURER,'Maker'),
    FieldValue(MetadataField.MPN,'R-123B')))
panel.preview(proposed)
assert panel.comparison.item(0,0).checkState()==Qt.CheckState.Unchecked
assert 'conflit' in panel.comparison.item(0,0).text()
for name,size in [('normal',(1200,800)),('narrow',(900,680)),('wide',(1600,950))]:
    window.resize(*size)
    capture('conflict-'+name)
panel.comparison.item(0,0).setCheckState(Qt.CheckState.Checked)
panel.accept_button.click()
assert 'Confirmer' in panel.message.text()
assert service.identification(part.id).value(MetadataField.MANUFACTURER)=='User Maker'
panel.replace_values.setChecked(True)
panel.accept_button.click()
assert service.identification(part.id).value(MetadataField.MANUFACTURER)=='Maker'
assert service.identification(part.id).value(MetadataField.MPN)=='R-123B'
assert catalogue.require(Part,part.id).description=='User description retained'
assert 'User Maker' in panel.history.toPlainText()
window.components_panel.search.setText('R-123B')
row = next(i for i,p in enumerate(window.components_panel.entities) if p.id==part.id)
assert not window.components_panel.table.isRowHidden(row)
panel.tabs.setCurrentIndex(1)
panel.document_form_toggle.click()
assert panel.document_stack.currentIndex()==1
assert service.configuration()==DatasheetConfiguration()
panel.pdfs.setCurrentIndex(panel.pdfs.findData(str(original.id)))
panel.doc_revision.setText('A')
panel.doc_date.setText('bad date')
panel.existing_button.click()
assert 'Date' in panel.message.text() and service.documents(part.id)==()
capture('document-form-error')
panel.doc_date.setText('2026-10-01')
panel.doc_language.setText('fr')
panel.existing_button.click()
assert len(service.documents(part.id))==1
assert catalogue.require(Asset,original.id)==original
assert resolver.choices(part)[0].asset_id==original.id
local_file = root / 'new.pdf'
local_file.write_bytes(PDF+b'\nnew local revision')
QFileDialog.getOpenFileName = staticmethod(lambda *args,**kwargs:(str(local_file),'PDF'))
panel.document_form_toggle.click()
panel.doc_title.setText('Local revision B')
panel.doc_revision.setText('B')
panel.local_button.click()
assert len(service.documents(part.id))==2
for name,size in [('normal',(1200,800)),('narrow',(900,680)),('wide',(1600,950))]:
    window.resize(*size)
    capture('documents-'+name)
panel.document_form_toggle.click()
for name,size in [('normal',(1200,800)),('narrow',(900,680)),('wide',(1600,950))]:
    window.resize(*size)
    capture('document-form-'+name)
panel.doc_title.setText('Manufacturer revision C')
panel.doc_source.setText('Declared manufacturer')
panel.url.setText('https://docs.maker.example/r.pdf')
panel.download_button.click()
assert 'désactivé' in panel.message.text() and provider.calls==[]
panel.enabled.setChecked(True)
panel.domains.setText('docs.maker.example')
panel.configure()
panel.download_button.click()
assert not panel.parts.isEnabled()
assert not window.close()
wait_worker()
assert len(service.documents(part.id))==3
assert catalogue.require(Asset,original.id)==original
assert resolver.choices(part)[0].asset_id==original.id
assert service.documents(other.id)==()
capture('download-success')
provider.failure=True
panel.document_form_toggle.click()
panel.download_button.click()
wait_worker()
assert 'indisponible' in panel.message.text()
assert len(service.documents(part.id))==3
capture('download-failure')
service.provider=None
panel.download_button.click()
wait_worker()
assert 'absent' in panel.message.text()
capture('adapter-absent')
panel.enabled.setChecked(False)
panel.configure()
panel.tabs.setCurrentIndex(0)
for name,size in [('normal',(1200,800)),('narrow',(900,680)),('wide',(1600,950))]:
    window.resize(*size)
    capture('identification-form-'+name)
panel.fields[MetadataField.CATEGORY].setText('Resistors')
panel.preview_button.click()
panel.accept_button.click()
assert service.identification(part.id).value(MetadataField.CATEGORY)=='Resistors'
assert len(service.identification(part.id).history)==3
copy=root/'copy.pdf'
QFileDialog.getSaveFileName=staticmethod(lambda *args,**kwargs:(str(copy),'PDF'))
panel.tabs.setCurrentIndex(1)
panel.document_list.setCurrentRow(0)
panel.retrieve_button.click()
assert copy.read_bytes()==PDF
panel.document_form_toggle.click()
panel.doc_title.setText('Draft for original part')
panel.url.setText('https://docs.maker.example/old.pdf')
panel.parts.setCurrentIndex(panel.parts.findData(str(other.id)))
assert panel.doc_title.text()=='' and panel.url.text()==''
assert panel.document_stack.currentIndex()==0
assert panel.records==()
capture('empty-other-documents')
assert window.close()
app.processEvents()
engine.dispose()
print('M10 enrichment, conflicts, PDF preservation, authorization, '
      'failures and three sizes PASS')
print(captures)
"""


def test_documentation_offline_ui(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
