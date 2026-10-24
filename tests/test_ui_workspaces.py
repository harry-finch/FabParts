"""Task navigation and component workflow preserve existing persistence and qualification rules."""

import os
import subprocess
import sys
from pathlib import Path


def test_task_workspaces_and_component_workflow(tmp_path: Path) -> None:
    script = """
import socket, sys
from pathlib import Path
from dataclasses import replace
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
from kipartmanager.domain.entities import *
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.infrastructure.database import create_database_engine, migrate
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.resolver_dialog import ResolverDialog
from tests.test_validation import setup_case

def forbidden(*args, **kwargs):
    raise AssertionError('Network access attempted')
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
root = Path(sys.argv[1])
app = QApplication([])
engine = create_database_engine(root / 'database.sqlite3'); migrate(engine)
validation, resolver, part, package, library, assets = setup_case(root, engine)
catalogue = validation.catalogue
catalogue.initialize_defaults()
lab = next(i for i in catalogue.list_entities(Inventory) if i.name == 'Lab')
personal = next(i for i in catalogue.list_entities(Inventory) if i.name == 'Personal')
location = Location(name='Tiroir A2'); catalogue.save(location)
catalogue.save(StockItem(part_id=part.id, inventory_id=lab.id,
    location_id=location.id, quantity=12))
catalogue.save(StockItem(part_id=part.id, inventory_id=personal.id, quantity=4))
other = Part(name='Unresolved'); catalogue.save(other)
pdf = root / 'sheet.pdf'; pdf.write_bytes(b'%PDF opaque fixture')
imports = AssetImports(catalogue, catalogue.store)
sheet = imports.import_file(str(pdf), name='Datasheet R')
part = catalogue.require(Part, part.id)
catalogue.save(replace(part, asset_ids=(*part.asset_ids, sheet.id)))
kinds = (Part, Package, Asset, Collection, Inventory, StockItem, Location)
before = {kind: catalogue.list_entities(kind) for kind in kinds}
index = LocalKiCadIndex(root / 'index')
window = MainWindow(catalogue, imports, KiCadLibraries(index), resolver, validation)
window.show(); app.processEvents()
assert [window.navigation.item(i).text() for i in range(window.navigation.count())] == [
    'Composants', 'Inventaire', 'Bibliothèques', 'KiCad local', 'Paramètres']
assert window.tabs.currentWidget() is window.component_workspace
panel = window.components_panel
row = next(i for i,p in enumerate(panel.entities) if p.id == part.id)
panel.table.selectRow(row)
assert panel.table.item(row, 4).text() == '12'
assert panel.table.item(row, 2).text() == '2/4 choisis'
assert 'Lab : 12' in panel.stock_summary.text() and 'Personal : 4' in panel.stock_text.text()
assert panel.package_name.text() == 'Package · R'
assert panel.resource_rows[AssetType.SYMBOL].origin.text() == 'User provided'
assert 'Non sélectionné' in panel.resource_rows[AssetType.DATASHEET].name.text()
assert '1 fichier(s) associé(s)' in panel.resource_rows[AssetType.DATASHEET].name.text()
assert panel.resource_rows[AssetType.MODEL_3D].action.isEnabled()
assert panel.technical.isHidden()
assert panel.next_action == 'identify'
assert {kind: catalogue.list_entities(kind) for kind in kinds} == before

# One role action still targets the shared package using the existing resolver.
original_exec = ResolverDialog.exec
seen = []
def choose_same(dialog):
    assert dialog.role.currentData() == AssetType.FOOTPRINT.value
    assert dialog.target().id == package.id
    dialog.query.setText('R'); dialog.search()
    dialog.items.setCurrentRow(0); dialog.select()
    seen.append(True)
    return QDialog.DialogCode.Accepted
ResolverDialog.exec = choose_same
panel.resource_action(AssetType.FOOTPRINT)
ResolverDialog.exec = original_exec
assert seen == [True]
assert resolver.choices(catalogue.require(Package, package.id))[0].asset_id == assets[1].id

# UI progress derives from real state and current qualification, not invented Part states.
part = catalogue.require(Part, part.id)
catalogue.save(replace(part, state=PartState.IDENTIFIED))
window.refresh()
assert panel.next_action == 'verify'
validation.validate(part)
panel.show_details()
assert panel.qualification_badge.text() == 'PASS'
assert panel.next_action == 'library'
assert '! Non sélectionné' in panel.resource_rows[AssetType.MODEL_3D].name.text()
labparts = next(c for c in catalogue.list_entities(Collection) if c.name == 'LabParts')
panel.collections.setCurrentIndex(panel.collections.findData(str(labparts.id)))
panel.add_button.click()
assert part.id in catalogue.require(Collection, labparts.id).part_ids
assert catalogue.require(Part, part.id).state == PartState.IDENTIFIED
panel.add_button.click()
assert catalogue.require(Collection, labparts.id).part_ids.count(part.id) == 1
assert 'PUBLISH' in panel.workflow.publication.text()
assert '✓' not in panel.workflow.publication.text()

# Editing an input invalidates the visible qualification without changing M5 rules.
part = catalogue.require(Part, part.id)
catalogue.save(replace(part, description='Changed input'))
window.refresh()
assert panel.qualification_badge.text() == 'STALE'
assert panel.next_action == 'verify'

# Already imported datasheets remain selectable without importing a duplicate.
def unexpected_import(*args, **kwargs):
    raise AssertionError('Existing datasheet incorrectly requires a second import')
QFileDialog.getOpenFileName = unexpected_import
def choose_sheet(dialog):
    assert dialog.role.currentData() == AssetType.DATASHEET.value
    assert dialog.target().id == part.id
    dialog.items.setCurrentRow(0); dialog.select()
    return QDialog.DialogCode.Accepted
ResolverDialog.exec = choose_sheet
panel.resource_action(AssetType.DATASHEET)
ResolverDialog.exec = original_exec
assert any(c.asset_id == sheet.id for c in resolver.choices(catalogue.require(Part, part.id)))
assert panel.qualification_badge.text() == 'STALE'
validation.validate(part)
panel.show_details()
assert panel.qualification_badge.text() == 'WARNING'
assert panel.next_action == 'verify'
validation.validate(part, accept_warnings=True)
panel.show_details()
assert panel.next_action == 'library'

panel.open_stock()
assert window.tabs.currentWidget() is window.inventory_workspace
stock = window.entity_panels[StockItem]
assert stock.part_id == part.id
window.inventory_filter.setCurrentIndex(window.inventory_filter.findData(str(lab.id)))
visible = [s for i,s in enumerate(stock.entities) if not stock.items.item(i).isHidden()]
assert len(visible) == 1 and visible[0].quantity == 12
assert 'Tiroir A2' in stock.items.item(stock.entities.index(visible[0])).text()
window.clear_stock_part()
window.inventory_filter.setCurrentIndex(0)
assert sum(not stock.items.item(i).isHidden() for i in range(stock.items.count())) == 2
window.open_packages(); assert window.component_workspace.currentIndex() == 1
window.open_assets(); assert window.component_workspace.currentIndex() == 2
window.open_libraries(); assert window.tabs.currentWidget() is window.entity_panels[Collection]
window.open_kicad_configuration(); assert window.kicad_panel.config_toggle.isChecked()
assert window.tabs.currentWidget() is window.kicad_panel
window.component_workspace.setCurrentIndex(0)
window.show_page(window.component_workspace)
panel.detail_stack.currentWidget().verticalScrollBar().setValue(500)
panel.message.show_message('Previous component message', 'success')
panel.search.setText('Unresolved')
panel.table.selectRow(next(i for i,p in enumerate(panel.entities) if p.id == other.id))
assert panel.message.text() == ''
assert panel.detail_stack.currentWidget().verticalScrollBar().value() == 0
assert '! Aucun package' in panel.package_name.text()
assert not panel.resource_rows[AssetType.FOOTPRINT].action.isEnabled()
assert panel.resource_rows[AssetType.SYMBOL].action.isEnabled()
assert catalogue.require(Part, other.id).state == PartState.DRAFT
# A deprecated identity must not suggest the domain-forbidden re-identification.
catalogue.save(replace(catalogue.require(Part, other.id), state=PartState.DEPRECATED))
window.refresh()
assert panel.badge.text() == 'DEPRECATED'
assert panel.context_button.text() == 'Composant déprécié'
assert not panel.context_button.isEnabled()
assert panel.selection_actions[0].isEnabled()  # Metadata remains editable.
window.close(); engine.dispose()
print('Offline UX workspaces, role routing, stock filters and library workflow PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
