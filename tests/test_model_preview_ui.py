"""Offline 3D inspection, interactions, entry points and worker lifetime."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import socket
import sys
import threading
from pathlib import Path
from PySide6.QtCore import QEventLoop,QTimer,Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.previews import Mesh, Previews
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.entities import Asset,AssetOrigin,AssetType,Package,Part
from kipartmanager.domain.kicad import LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.database import create_database_engine,migrate
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.preview_reader import LocalPreviewReader
from kipartmanager.infrastructure import model_preview
from kipartmanager.ui.main_window import MainWindow
from kipartmanager.ui.model_view import ModelView
from kipartmanager.ui.preview_dialog import PreviewDialog
from tests.test_model_previews import WRL

def forbidden(*args,**kwargs):raise AssertionError('Network used during local 3D preview')
socket.create_connection=forbidden;socket.getaddrinfo=forbidden
socket.socket.connect=forbidden;socket.socket.connect_ex=forbidden
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
app=QApplication([])
# Intersecting projected triangles require depth per pixel, not face-centroid sorting.
surface=ModelView(None);surface.resize(400,300)
overlap=Mesh(vertices=((-1.,-1.,-1.),(1.,-1.,1.),(0.,1.,0.),
                       (-1.,-1.,0.),(1.,-1.,0.),(0.,1.,0.)),
             faces=((0,1,2),(3,4,5)),colors=((.9,.1,.1),(.1,.1,.9)))
surface.display(overlap);surface.standard_view(1)
image=surface.raster(overlap)
left=image.pixelColor(round(image.width()*175/400),round(image.height()*170/300))
right=image.pixelColor(round(image.width()*225/400),round(image.height()*170/300))
assert left.blue()>left.red() and right.red()>right.blue()

engine=create_database_engine(root/'db.sqlite3');migrate(engine)
repository=SqliteCatalogue(engine);store=LocalAssetStore(root/'assets')
catalogue=Catalogue(repository,store);catalogue.initialize_defaults()
imports=AssetImports(catalogue,store)
asset=imports.import_content(WRL.encode(),'fixture.wrl',name='Package 3D',
 origin=AssetOrigin.USER_PROVIDED,source_reference='local fixture')
package=Package(name='Fixture',asset_ids=(asset.id,));catalogue.save(package)
part=Part(name='Part 3D',package_id=package.id);catalogue.save(part)
folder=root/'official'/'Fixture.3dshapes';folder.mkdir(parents=True)
(folder/'model.wrl').write_bytes(WRL.encode())
index=LocalKiCadIndex(root/'index');index.configure(LibraryRoots(models=str(folder.parent)))
index.rebuild(index.configuration())
reader=LocalPreviewReader(store,index);service=Previews(catalogue,reader)
libraries=KiCadLibraries(index);resolver=LocalResolver(catalogue,repository,libraries)
resolver.select(package,resolver.search(package,AssetType.MODEL_3D,asset.name).candidates[0])
window=MainWindow(catalogue,imports,libraries,resolver,previews=service);window.show()
def pump():
 loop=QEventLoop();QTimer.singleShot(25,loop.quit);loop.exec()
def loaded(dialog):
 for i in range(400):
  pump()
  if dialog.worker is None:return
 raise AssertionError('3D worker not completed')
def latest():return window.findChildren(PreviewDialog)[-1]
choice=ResourceChoice(AssetType.MODEL_3D,asset_id=asset.id)
window.inspect_resource(choice);dialog=latest();loaded(dialog)
assert not dialog.isModal() and dialog.model_view.mesh is not None
assert dialog.stack.currentWidget() is dialog.model_view
assert not dialog.entries.isVisible() and dialog.views.isVisible()
assert dialog.plus.isEnabled() and asset.file.sha256 in dialog.source.toPlainText()
original=dialog.model_view.magnification;dialog.plus.click()
assert dialog.model_view.magnification>original
view=dialog.model_view
for kind,buttons,pos in [(QEvent.Type.MouseButtonPress,Qt.MouseButton.LeftButton,QPointF(30,30)),
 (QEvent.Type.MouseMove,Qt.MouseButton.LeftButton,QPointF(80,50)),
 (QEvent.Type.MouseButtonRelease,Qt.MouseButton.NoButton,QPointF(80,50))]:
 button=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
 app.sendEvent(view,QMouseEvent(kind,pos,view.mapToGlobal(pos.toPoint()),button,buttons,Qt.KeyboardModifier.NoModifier))
assert view.yaw != -35.
dialog.views.setCurrentIndex(1);assert (view.yaw,view.pitch)==(0.,0.)
view.pan=QPointF(40,10);dialog.fit_button.click()
assert view.magnification==1 and view.pan==QPointF()
for width,height in [(900,680),(1200,800),(1600,950)]:
 dialog.resize(width,height);pump()
 assert view.width()>300 and view.height()>180
 dialog.grab().save(str(root/f'model-{width}.png'))
dialog.close();pump()
# The component, files, official index and resolver all expose the same inspector.
cp=window.components_panel
row=next(i for i,p in enumerate(cp.entities) if p.id==part.id)
cp.table.selectRow(row);cp.show_details()
button=cp.resource_rows[AssetType.MODEL_3D].inspect
assert button.isEnabled();button.click();loaded(latest());latest().close();pump()
panel=window.entity_panels[Asset]
row=next(i for i,a in enumerate(panel.entities) if a.id==asset.id)
panel.items.setCurrentRow(row);assert panel.preview_button.isEnabled()
panel.preview_button.click();loaded(latest());latest().close();pump()
kicad=window.kicad_panel;kicad.query.setText('model');kicad.search();kicad.items.setCurrentRow(0)
assert kicad.preview_button.isEnabled();kicad.preview_button.click()
loaded(latest());assert latest().model_view.mesh;latest().close();pump()
resource=window.resource_dialog(package,window);resource.show()
resource.role.setCurrentIndex(resource.role.findData(AssetType.MODEL_3D.value));resource.search()
resource.items.setCurrentRow(0);assert resource.preview_button.isEnabled()
resource.preview_button.click();loaded(latest());latest().close();pump()
# Parent and preview cannot be destroyed while the worker owns its Qt objects.
release=threading.Event()
class SlowReader(LocalPreviewReader):
 def managed(self,file):
  assert release.wait(3)
  return super().managed(file)
resource.previews=Previews(catalogue,SlowReader(store,index))
resource.preview_button.click();dialog=latest();pump()
assert dialog.worker is not None and not dialog.close()
dialog.reject();assert dialog.isVisible()
resource.reject();assert resource.isVisible()
assert not window.close()
release.set();loaded(dialog);assert dialog.model_view.mesh
dialog.close();pump();resource.close();pump()
# Missing optional STEP backend is a visible recoverable error, not a startup failure.
model_preview.freecad_command=lambda:None
step=imports.import_content(b'ISO-10303-21;\nEND-ISO-10303-21;','fixture.step',name='STEP',
 origin=AssetOrigin.USER_PROVIDED,source_reference='local fixture')
window.inspect_resource(ResourceChoice(AssetType.MODEL_3D,asset_id=step.id))
dialog=latest();loaded(dialog)
assert 'FreeCAD' in dialog.message.text() and not dialog.plus.isEnabled()
dialog.grab().save(str(root/'missing-step-backend.png'));dialog.close();pump()
assert catalogue.require(Asset,asset.id)==asset
assert resolver.choices(package)[0].asset_id==asset.id
assert (folder/'model.wrl').read_bytes()==WRL.encode()
window.close();pump();engine.dispose()
"""


def test_model_preview_offline_ui(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
