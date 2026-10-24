"""Publication transfer UI exercises preview, conflicts and catalogue refresh."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = """
import socket, sys
from dataclasses import replace
from pathlib import Path
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtTest import QTest
from tests.test_validation import setup_case
from tests.test_publisher import local_probe
from kipartmanager.application.bundles import Bundles
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.publications import Publications
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.application.validation import LocalValidation
from kipartmanager.infrastructure.bundles import LocalBundles
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.infrastructure.publications import LocalPublications
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
from kipartmanager.domain.entities import Collection, Part
from kipartmanager.ui.main_window import MainWindow

def forbidden(*args, **kwargs): raise AssertionError("Network attempted")
socket.create_connection=forbidden; socket.getaddrinfo=forbidden; socket.socket.connect=forbidden
root=Path(sys.argv[1]).resolve(); root.mkdir(exist_ok=True)
captures=Path(sys.argv[2]) if len(sys.argv)>2 else None
if captures: captures.mkdir(exist_ok=True)
app=QApplication([])
engine=create_database_engine(root/'source/database.sqlite3'); migrate(engine)
validation, _, part, _, collection, _=setup_case(root/'source', engine)
validation.catalogue.initialize_defaults(); validation.validate(collection)
builder=LocalLibraryBuilder(local_probe(validation).store,LocalKiCadIndex(root/'source'),root/'source')
history=LocalPublications(root/'source/publications',builder)
publications=Publications(LocalPublisher(validation.catalogue,validation,builder),history)
record=publications.publish(collection,1)
bundles=Bundles(LocalBundles(validation.catalogue.repository,history))
source=MainWindow(validation.catalogue,publications=publications,bundles=bundles)
source.show(); app.processEvents()
source.show_page(source.publications_panel)
panel=source.publications_panel
panel.collections.setCurrentIndex(panel.collections.findData(str(collection.id)))
panel.items.setCurrentRow(0)
assert panel.export_button.isEnabled()
archive=root/'transfer.kiparts'
QFileDialog.getSaveFileName=lambda *a,**k:(str(archive),'')
panel.export_button.click()
assert archive.exists(),panel.message.text()
panel.export_button.click()
assert panel.message.property('tone')=='error'
target_root=root/'target'
target_engine=create_database_engine(target_root/'database.sqlite3'); migrate(target_engine)
store=LocalAssetStore(target_root/'assets');repo=SqliteCatalogue(target_engine)
catalogue=Catalogue(repo,store);catalogue.initialize_defaults()
index=LocalKiCadIndex(target_root);builder2=LocalLibraryBuilder(store,index,target_root)
validation2=LocalValidation(catalogue,LocalResourceProbe(store,index),SqliteValidationReports(target_engine))
history2=LocalPublications(target_root/'publications',builder2)
pub2=Publications(LocalPublisher(catalogue,validation2,builder2),history2)
destination=MainWindow(catalogue,validation=validation2,publications=pub2,bundles=Bundles(LocalBundles(repo,history2)))
source.close();destination.show();destination.show_page(destination.publications_panel)
panel2=destination.publications_panel
def snap(name):
 app.processEvents();QTest.qWait(120);app.processEvents()
 if captures: destination.grab().save(str(captures/(name+'.png')))
snap('empty')
assert not panel2.export_button.isEnabled()
QFileDialog.getOpenFileName=lambda *a,**k:(str(archive),'')
panel2.import_button.click()
assert panel2.confirm_import.isEnabled(),panel2.message.text()
assert '1 composant(s)' in panel2.import_summary.toPlainText()
for width,height,name in [(1200,800,'normal'),(900,680,'narrow'),(1600,950,'wide')]:
 destination.resize(width,height);snap('preview-'+name)
panel2.confirm_import.click();snap('import-success')
for width,height,name in [(1200,800,'normal'),(900,680,'narrow'),(1600,950,'wide')]:
 destination.resize(width,height);snap('selected-'+name)
destination.resize(1200,800)
assert panel2.selected()==record,panel2.message.text()
assert panel2.message.property('tone')=='success'
assert len(destination.components_panel.entities)==1
panel2.verify_button.click();assert panel2.badge.text()=='PASS'
panel2.destination.setText(str(root/'portable-kicad'))
panel2.rebuild_button.click()
assert (root/'portable-kicad').is_dir(), panel2.message.text()
snap('verified-rebuilt')
panel2.inspect_archive(str(archive));assert panel2.confirm_import.isEnabled()
panel2.confirm_import.click();assert len(repo.list_entities(Part))==1
current=repo.get(Part,part.id);repo.save(replace(current,name='Local modified part'))
panel2.inspect_archive(str(archive))
assert not panel2.confirm_import.isEnabled()
assert 'UUID' in panel2.import_summary.toPlainText();snap('conflict')
panel2.inspect_archive(str(root/'missing.kiparts'))
assert panel2.message.property('tone')=='error'
assert not panel2.import_card.isVisible();snap('invalid-archive')
destination.close();engine.dispose();target_engine.dispose()
print('M8 UI offline workflow PASS',root)
"""


def test_bundle_ui(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
