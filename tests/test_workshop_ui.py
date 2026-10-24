"""Workshop presentation keeps sorting, editing and optional assistance tied to identity."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import sys
from pathlib import Path
from dataclasses import replace
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from tests.test_validation import setup_case
from tests.test_assistance import FixtureAssistant
from kipartmanager.application.assistance import Assistance
from kipartmanager.application.documentation import Documentation
from kipartmanager.domain.documentation import (
    MetadataField, MetadataProposal, MetadataSource, FieldValue
)
from kipartmanager.domain.entities import Part, PartState, Inventory, StockItem, Package
from kipartmanager.infrastructure.assistance import AssistanceToml
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.documentation import SqliteDocumentation, LocalProposalReader
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.entity_dialog import EntityDialog
root=Path(sys.argv[1]); app=QApplication([])
engine=create_database_engine(root/'database.sqlite3'); migrate(engine)
validation,resolver,part,package,collection,assets=setup_case(root,engine)
catalogue=validation.catalogue; catalogue.initialize_defaults()
lab=next(i for i in catalogue.list_entities(Inventory) if i.name=='Lab')
a=Part(name='Alpha')
z=Part(name='Zener')
catalogue.save(a); catalogue.save(z)
catalogue.save(replace(a,state=PartState.IDENTIFIED))
catalogue.save(StockItem(part_id=a.id,inventory_id=lab.id,quantity=100))
catalogue.save(StockItem(part_id=z.id,inventory_id=lab.id,quantity=2))
docs=Documentation(catalogue,SqliteDocumentation(engine),LocalProposalReader(),ManufacturerSettings(root))
assistant=Assistance(AssistanceToml(root),FixtureAssistant())
window=MainWindow(catalogue,resolver=resolver,validation=validation,documentation=docs,assistance=assistant)
window.show(); app.processEvents(); panel=window.components_panel
assert app.palette().color(QPalette.ColorRole.Window).lightness()<70
assert app.palette().color(QPalette.ColorRole.Text).lightness()>190
panel.table.selectRow(next(i for i,p in enumerate(panel.entities) if p.id==z.id))
panel.sort_by_column(4)
assert [panel.table.item(i,4).text() for i in range(3)]==['0','2','100']
assert panel.selected().id==z.id
assert panel.name.text()=='Zener'
panel.sort_by_column(4)
assert [panel.table.item(i,4).text() for i in range(3)]==['100','2','0']
assert panel.selected().id==z.id
panel.state_filter.setCurrentIndex(panel.state_filter.findData('IDENTIFIED'))
assert panel.selected() is None
assert [panel.entities[i].id for i in range(3) if not panel.table.isRowHidden(i)]==[a.id]
panel.state_filter.setCurrentIndex(0)
panel.table.selectRow(next(i for i,p in enumerate(panel.entities) if p.id==part.id))
for width,height in ((900,680),(1200,800),(1600,950)):
    window.resize(width,height); app.processEvents()
    scroll=panel.detail_stack.currentWidget()
    assert scroll.widget().width()<=scroll.viewport().width()
    for row in panel.resource_rows.values():
        assert row.title.width()>30
        assert row.action.geometry().right()<row.width()
before=(catalogue.list_entities(Part),catalogue.list_entities(Package))
panel.edit(True); app.processEvents()
editor=window.editor
assert isinstance(editor,EntityDialog) and not editor.isModal() and editor.isVisible()
editor.name.setText('R edited')
panel.edit_package(); assert window.editor is editor
assert not window.close() # The open draft is not discarded by closing its owner.
editor.save(); app.processEvents()
assert window.editor is None
assert catalogue.require(Part,part.id).name=='R edited'
assert catalogue.list_entities(Package)==before[1]
assert resolver.choices(catalogue.require(Part,part.id))[0].asset_id==assets[0].id
assert docs.identification(part.id).value(MetadataField.MPN)==''
panel.table.selectRow(next(i for i,p in enumerate(panel.entities) if p.id==part.id))
panel.ai_button.click(); app.processEvents()
documentation=window.documentation_panel
assert documentation.tabs.currentWidget() is documentation.assistance_panel
assert documentation.parts.currentData()==str(part.id)
assert documentation.assistance_panel.request is None
assert not documentation.assistance_panel.consent.isChecked()
assert not documentation.assistance_panel.send_button.isEnabled()
documentation.preview(MetadataProposal(MetadataSource('Fixture','fixture:source-to-clear'),
    (FieldValue(MetadataField.MPN,'proposed'),)))
assert documentation.proposal_reference.toPlainText()=='fixture:source-to-clear'
window.open_documentation(z)
assert documentation.proposal_reference.toPlainText()==''
window.close(); app.processEvents(); engine.dispose()
"""


def test_workshop_identity_and_optional_assistance(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
