"""Offline build action, qualification errors and successful new output folder."""

import os
import subprocess
import sys
from pathlib import Path


def test_publisher_offline_ui(tmp_path: Path) -> None:
    script = """
import socket
import sys
from pathlib import Path

def forbidden(*args,**kwargs):raise AssertionError('Network attempted')
socket.create_connection=socket.getaddrinfo=socket.socket.connect=socket.socket.connect_ex=forbidden
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.application.validation import LocalValidation
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.domain.entities import AssetType,Collection,Part,Package
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine,migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.publisher_dialog import PublisherDialog
root=Path(sys.argv[1]).resolve();app=QApplication([])
engine=create_database_engine(root/'data/database/catalogue.sqlite3');migrate(engine)
store=LocalAssetStore(root/'data/assets');repo=SqliteCatalogue(engine);catalogue=Catalogue(repo,store)
index=LocalKiCadIndex(root/'data');resolver=LocalResolver(catalogue,repo)
validation=LocalValidation(catalogue,LocalResourceProbe(store,index),SqliteValidationReports(engine))
publisher=LocalPublisher(catalogue,validation,LocalLibraryBuilder(store,index,root/'data'))
package=Package(name='R');catalogue.save(package)
part=Part(name='R',package_id=package.id);catalogue.save(part)
collection=Collection(name='LabParts',part_ids=(part.id,));catalogue.save(collection)
contents={'.kicad_sym':'(kicad_symbol_lib (version 20251024) (symbol "R" (symbol "R_1_1" '
 '(pin passive line (at 0 0 0) (length 1) (name "A") (number "1")))))',
 '.kicad_mod':'(footprint "R" (version 20260206) (pad "1" smd rect (at 0 0) (size 1 1) '
 '(layers "F.Cu")))'}
for extension,role in (('.kicad_sym',AssetType.SYMBOL),('.kicad_mod',AssetType.FOOTPRINT)):
 source=root/('R'+extension);source.write_text(contents[extension])
 AssetImports(catalogue,store).import_file(str(source),name='R')
 owner=part if role is AssetType.SYMBOL else package
 resolver.select(owner,resolver.search(owner,role,'R').candidates[0])
window=MainWindow(catalogue,resolver=resolver,validation=validation,publisher=publisher);window.show()
window.panels[6].items.setCurrentRow(0);verified=[]
def drive():
 dialog=QApplication.activeModalWidget();assert isinstance(dialog,PublisherDialog)
 dialog.build_button.click();assert 'Choisir' in dialog.status.text()
 dialog.destination.setText(str(root/'output'));dialog.build_button.click()
 assert 'non publiable' in dialog.status.text() and not (root/'output').exists()
 validation.validate(collection);dialog.build_button.click()
 assert 'Construction terminée' in dialog.status.text()
 assert (root/'output/fp-lib-table').exists() and (root/'output/sym-lib-table').exists()
 assert not (root/'output/BUILDING').exists()
 dialog.build_button.click();assert 'existante' in dialog.status.text()
 verified.append(True);dialog.accept()
QTimer.singleShot(50,drive);window.panels[6].publish();assert verified==[True]
window.close();app.processEvents();engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
