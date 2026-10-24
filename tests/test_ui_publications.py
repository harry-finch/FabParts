"""The publication page keeps historical actions independent of current collection edits."""

import os
import subprocess
import sys
from pathlib import Path


def test_publication_page_workflow(tmp_path: Path) -> None:
    script = """
import sys, socket
from pathlib import Path
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from tests.test_validation import setup_case
from tests.test_publisher import local_probe
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.application.publications import Publications
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
from kipartmanager.infrastructure.publications import LocalPublications
from kipartmanager.ui.main_window import MainWindow

def forbidden(*args, **kwargs):
    raise AssertionError('Network access attempted')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
root=Path(sys.argv[1]); data=root/'data'; data.mkdir()
app=QApplication([])
engine=create_database_engine(data/'database.sqlite3'); migrate(engine)
validation, _, part, _, collection, _ = setup_case(data, engine)
validation.catalogue.initialize_defaults()
validation.validate(collection)
builder=LocalLibraryBuilder(local_probe(validation).store,LocalKiCadIndex(data),data)
service=Publications(LocalPublisher(validation.catalogue,validation,builder),LocalPublications(data/'publications',builder))
window=MainWindow(validation.catalogue,publications=service)
window.show(); app.processEvents()
assert window.navigation.count()==5
window.tabs.setCurrentWidget(window.publications_panel)
panel=window.publications_panel
assert panel is not None
assert panel.history.currentWidget() is panel.empty
assert not panel.publish_button.isEnabled()
assert not panel.verify_button.isEnabled()
panel.collections.setCurrentIndex(panel.collections.findData(str(collection.id)))
assert panel.version.value()==1
panel.publish_button.click()
assert len(panel.records)==1, panel.message.text()
assert panel.version.value()==2
assert panel.selected().version==1
assert panel.badge.text()=='PUBLISHED'
panel.verify_button.click()
assert panel.badge.text()=='PASS'
assert panel.message.property('tone')=='success'
part=validation.catalogue.require(type(part),part.id)
validation.catalogue.save(replace(part,name='Current catalogue changed'))
panel.destination.setText(str(root/'rebuilt'))
panel.rebuild_button.click()
assert (root/'rebuilt').is_dir(), panel.message.text()
assert panel.message.property('tone')=='success'
panel.rebuild_button.click()
assert panel.message.property('tone')=='error'
panel.publish_button.click()
assert panel.message.property('tone')=='error'
assert len(service.list_publications())==1
panel.collections.setCurrentIndex(0)
assert not panel.publish_button.isEnabled()
assert len(panel.records)==1
window.close();engine.dispose()
print('M7 UI offline workflow PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
