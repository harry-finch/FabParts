"""Regression checks for navigation and filtering without changing catalogue data."""

import os
import subprocess
import sys
from pathlib import Path


def test_navigation_filter_and_selection(tmp_path: Path) -> None:
    script = """
from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import Part
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.components import MessageBanner
app = QApplication([])
engine = create_database_engine(Path(sys.argv[1]) / 'catalogue.sqlite3')
migrate(engine)
service = Catalogue(SqliteCatalogue(engine))
service.initialize_defaults()
service.save(Part(name='Resistor'))
service.save(Part(name='Capacitor'))
window = MainWindow(service)
window.show()
app.processEvents()
window.navigation.setCurrentRow(2)
assert window.tabs.currentIndex() == 2
window.tabs.setCurrentIndex(0)
assert window.navigation.currentRow() == 0
panel = window.panels[0]
panel.search.setText('RESISTOR')
row = next(i for i in range(panel.table.rowCount()) if not panel.table.isRowHidden(i))
panel.table.selectRow(row)
selected = panel.entities[row].id
assert panel.name.text() == "Resistor"
assert str(selected) not in panel.name.text()
assert str(selected) in panel.technical.text()
assert panel.technical.isHidden()
assert str(selected) not in panel.table.item(row, 0).text()
assert all(button.isEnabled() for button in panel.selection_actions)
panel.refresh()
assert panel.entities[panel.table.currentRow()].id == selected
assert panel.search.text() == 'RESISTOR'
panel.search.setText('No matching component')
assert panel.list_stack.currentWidget() is panel.empty
assert panel.table.currentRow() == -1
assert all(not button.isEnabled() for button in panel.selection_actions)
assert len(service.list_entities(Part)) == 2
panel.search.clear()
assert panel.list_stack.currentWidget() is panel.table
banner = MessageBanner()
banner.show_message('Failure', 'error')
assert banner.property('tone') == 'error'
banner.setText('Successful next operation')
assert banner.property('tone') == 'info'
banner.show()
for width in (300, 500, 300, 500):
    banner.resize(width, 120)
    app.processEvents()
    assert 0 < banner.minimumHeight() < 120
banner.close()
window.close()
engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
