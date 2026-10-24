"""Offline Qt report review, explicit warning acknowledgement and stale gate."""

import os
import subprocess
import sys
from pathlib import Path


def test_validation_offline_ui(tmp_path: Path) -> None:
    script = """
import socket
import sys
from pathlib import Path
from dataclasses import replace

def forbidden(*args,**kwargs):
    raise AssertionError("Network access attempted")
socket.create_connection=forbidden
socket.getaddrinfo=forbidden
socket.socket.connect=forbidden
socket.socket.connect_ex=forbidden
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from sqlalchemy import text
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.entities import AssetType,Collection,Package,Part
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine,migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.validation_dialog import ValidationDialog
root=Path(sys.argv[1]).resolve()
app=QApplication([])
engine=create_database_engine(root/'database/catalogue.sqlite3');migrate(engine)
store=LocalAssetStore(root/'assets');repo=SqliteCatalogue(engine);catalogue=Catalogue(repo,store)
index=LocalKiCadIndex(root/'data');resolver=LocalResolver(catalogue,repo)
service=LocalValidation(catalogue,LocalResourceProbe(store,index),SqliteValidationReports(engine))
package=Package(name='R package');catalogue.save(package)
part=Part(name='R',package_id=package.id);catalogue.save(part)
collection=Collection(name='Test collection',part_ids=(part.id,));catalogue.save(collection)
contents={'.kicad_sym':'(kicad_symbol_lib (version 20251024) (symbol "R" (symbol "R_1_1" '
  '(pin passive line (at 0 0 0) (length 1) (name "A") (number "1")))))',
 '.kicad_mod':'(footprint "R" (version 20260206) (pad "1" smd rect (at 0 0) (size 1 1) '
  '(layers "F.Cu")))', '.step':'ISO-10303-21; END-ISO-10303-21;'}
for extension,role in (('.kicad_sym',AssetType.SYMBOL),
                       ('.kicad_mod',AssetType.FOOTPRINT),('.step',AssetType.MODEL_3D)):
    source=root/('R'+extension);source.write_text(contents[extension])
    AssetImports(catalogue,store).import_file(str(source),name='R')
    owner=part if role is AssetType.SYMBOL else package
    resolver.select(owner,resolver.search(owner,role,'R').candidates[0])
window=MainWindow(catalogue,resolver=resolver,validation=service);window.show()
window.panels[6].items.setCurrentRow(0)
verified=[]
def drive():
    dialog=QApplication.activeModalWidget();assert isinstance(dialog,ValidationDialog)
    assert 'UNCHECKED' in dialog.status.text()
    dialog.accept_warnings.setChecked(True);dialog.validate_button.click()
    assert 'rapport actuel' in dialog.status.text()
    dialog.accept_warnings.setChecked(False);dialog.validate_button.click()
    assert 'WARNING' in dialog.status.text()
    assert not service.qualification(collection).eligible
    assert any('SHA-256 :' in dialog.items.item(i).text() for i in range(dialog.items.count()))
    dialog.accept_warnings.setChecked(True);dialog.validate_button.click()
    assert service.require_publishable(collection)
    assert not dialog.accept_warnings.isChecked()
    current=catalogue.require(Part,part.id);catalogue.save(replace(current,description='modified'))
    dialog.refresh_button.click();assert 'STALE' in dialog.status.text()
    assert not service.qualification(collection).eligible
    dialog.accept_warnings.setChecked(True);dialog.validate_button.click()
    assert 'rapport actuel' in dialog.status.text()
    verified.append(True);dialog.accept()
QTimer.singleShot(50,drive);window.panels[6].validate_local();assert verified==[True]
window.close();app.processEvents();engine.dispose()
engine=create_database_engine(root/'database/catalogue.sqlite3');migrate(engine)
repo=SqliteCatalogue(engine);catalogue=Catalogue(repo,store)
service=LocalValidation(catalogue,LocalResourceProbe(store,index),SqliteValidationReports(engine))
assert service.qualification(collection).state=='STALE'
assert service.qualification(collection).report.warnings_accepted
service.validate(collection);service.validate(collection,accept_warnings=True)
assert service.require_publishable(collection)
with engine.begin() as connection:
    connection.execute(text("UPDATE validation_reports SET report_json='invalid'"))
dialog=ValidationDialog(service,collection);dialog.show()
assert 'illisible' in dialog.status.text()
dialog.validate_button.click();assert 'WARNING' in dialog.status.text()
assert not service.qualification(collection).eligible
dialog.close();app.processEvents()
empty=Collection(name='Empty');catalogue.save(empty)
dialog=ValidationDialog(service,empty);dialog.show();dialog.validate_button.click()
assert 'ERROR' in dialog.status.text()
assert not service.qualification(empty).eligible
dialog.close();app.processEvents();engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
