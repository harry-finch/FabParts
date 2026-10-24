"""Modeless, read-only KiCad/PDF/3D inspection with shared provenance and zoom."""

from typing import cast

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kipartmanager.application.previews import Drawing, Preview, Previews, Primitive
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ui.components import (
    DetailText,
    MessageBanner,
    PageHeader,
    PageLayout,
    label,
    origin_label,
)
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.model_view import ModelView
from kipartmanager.ui.theme import PREVIEW_COLORS

SCALE = 40.0


class DrawingView(QGraphicsView):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.canvas = QGraphicsScene(self)
        self.setScene(self.canvas)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setToolTip(
            "Zoom par molette ; glisser pour déplacer ; Recentrer pour ajuster à la fenêtre."
        )
        self.setBackgroundBrush(QColor(PREVIEW_COLORS["Background"]))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAccessibleName("Aperçu KiCad · glisser pour déplacer, molette pour zoomer")
        self.fitting = True
        self.annotations = False

    def display(self, drawing: Drawing) -> None:
        self.canvas.clear()
        for primitive in drawing.primitives:
            if primitive.kind != "annotation" or self.annotations:
                self.add(primitive)
        rect = self.canvas.itemsBoundingRect()
        self.canvas.setSceneRect(rect.adjusted(-SCALE, -SCALE, SCALE, SCALE))
        self.fit()

    def add(self, p: Primitive) -> None:
        colour = QColor(PREVIEW_COLORS.get(p.layer, PREVIEW_COLORS["Other"]))
        pen = QPen(colour, p.width * SCALE)
        if "CrtYd" in p.layer:
            pen.setStyle(Qt.PenStyle.DashLine)
        points = [QPointF(x * SCALE, y * SCALE) for x, y in p.points]
        if p.kind in {"text", "annotation"}:
            item = self.canvas.addSimpleText(p.text)
            item.setBrush(colour)
            font = item.font()
            font.setPixelSize(max(4, round(p.size * SCALE)))
            item.setFont(font)
            bounds = item.boundingRect()
            item.setPos(points[0] - bounds.center())
            item.setTransformOriginPoint(bounds.center())
            item.setRotation(p.angle)
            return
        path = QPainterPath()
        if p.kind.startswith("pad_"):
            w, h = p.points[1]
            rect = QRectF(-w * SCALE / 2, -h * SCALE / 2, w * SCALE, h * SCALE)
            if p.kind == "pad_ellipse":
                path.addEllipse(rect)
            elif p.kind in {"pad_round", "pad_oval"}:
                radius = min(w, h) * SCALE * (p.size if p.kind == "pad_round" else 0.5)
                path.addRoundedRect(rect, radius, radius)
            else:
                path.addRect(rect)
            item_path = self.canvas.addPath(path, pen, colour)
            item_path.setPos(points[0])
            item_path.setRotation(p.angle)
            return
        if p.kind in {"rect", "ellipse"}:
            rect = QRectF(points[0], points[1]).normalized()
            if p.kind == "rect":
                path.addRect(rect)
            else:
                path.addEllipse(rect)
        else:
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            if p.kind == "polygon":
                path.closeSubpath()
        brush = QColor(PREVIEW_COLORS["Fill"]) if p.filled else Qt.BrushStyle.NoBrush
        self.canvas.addPath(path, pen, brush)

    def fit(self) -> None:
        self.fitting = True
        self.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        value = self.transform().m11() * factor
        if 0.001 <= value <= 100:
            self.fitting = False
            self.scale(factor, factor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.fitting:
            self.fit()


class PreviewDialog(QDialog):
    def __init__(self, service: Previews, choice: ResourceChoice, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Inspecter une ressource")
        self.resize(980, 740)
        self.drawings: tuple[Drawing, ...] = ()
        self.kind = choice.asset_type
        self.source_text = ""
        layout = PageLayout(self)
        self.header = PageHeader("Aperçu", "Lecture seule · l’inspection ne vaut pas validation.")
        layout.addWidget(self.header)
        controls = QHBoxLayout()
        self.entries = QComboBox()
        self.entries.setMinimumContentsLength(12)
        self.entries.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.entries.setAccessibleName("Symbole, unité et représentation à afficher")
        self.entries.currentIndexChanged.connect(self.show_drawing)
        controls.addWidget(self.entries, 1)
        self.views = QComboBox()
        self.views.addItems(["Isométrique", "Dessus", "Face", "Droite"])
        self.views.setAccessibleName("Vue standard du modèle 3D")
        self.views.hide()
        controls.addWidget(self.views, 1)
        self.page = QSpinBox()
        self.page.setPrefix("Page ")
        self.page.setAccessibleName("Page du PDF")
        controls.addWidget(self.page)
        self.minus = QPushButton("−")
        self.minus.setAccessibleName("Réduire l’aperçu")
        self.plus = QPushButton("+")
        self.plus.setAccessibleName("Agrandir l’aperçu")
        self.fit_button = QPushButton("Recentrer")
        for button in (self.minus, self.plus, self.fit_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.stack = QStackedWidget()
        self.error_view = QWidget()
        error_layout = QVBoxLayout(self.error_view)
        error_layout.addStretch()
        error_layout.addWidget(label("Aperçu indisponible pour cette ressource", "heading"))
        error_layout.addStretch()
        self.stack.addWidget(self.error_view)
        self.drawing_view = DrawingView(self)
        self.model_view = ModelView(self)
        self.views.currentIndexChanged.connect(self.model_view.standard_view)
        self.stack.addWidget(self.model_view)
        self.pdf_view = QPdfView(self)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.stack.addWidget(self.drawing_view)
        self.stack.addWidget(self.pdf_view)
        layout.addWidget(self.stack, 1)
        self.legend = label("", "muted")
        layout.addWidget(self.legend)
        self.annotations = QCheckBox("Afficher les textes du footprint")
        self.annotations.setToolTip(
            "Références et valeurs du fichier ; les numéros de pads restent toujours visibles."
        )
        self.annotations.hide()
        self.annotations.toggled.connect(self.show_drawing)
        layout.addWidget(self.annotations)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        self.source_toggle = source_toggle = QPushButton("Provenance et détails de l’aperçu")
        source_toggle.setCheckable(True)
        layout.addWidget(source_toggle)
        self.source = DetailText("")
        self.source.hide()
        source_toggle.toggled.connect(self.source.setVisible)
        layout.addWidget(self.source)
        footer = QHBoxLayout()
        self.expand = QPushButton("Agrandir la fenêtre")
        self.expand.clicked.connect(self.toggle_size)
        footer.addWidget(self.expand)
        footer.addStretch()
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.minus.clicked.connect(lambda: self.zoom(1 / 1.2))
        self.plus.clicked.connect(lambda: self.zoom(1.2))
        self.fit_button.clicked.connect(self.fit)
        self.page.valueChanged.connect(self.go_page)
        self.document = QPdfDocument(self)
        self.document.statusChanged.connect(self.pdf_status)
        self.pdf_view.setDocument(self.document)
        self.pdf_view.pageNavigator().currentPageChanged.connect(self.page_changed)
        self.buffer = QBuffer(self)
        self.page.hide()
        self.worker: PreviewWorker | None = None
        if choice.asset_type is AssetType.MODEL_3D:
            self.entries.hide()
            self.views.show()
            self.views.setEnabled(False)
            self.set_controls(False)
            self.message.show_message("Lecture et préparation du modèle 3D local…")
            worker = PreviewWorker(service, choice, self)
            self.worker = worker
            worker.loaded.connect(self.preview_loaded)
            worker.failed.connect(self.preview_failed)
            worker.finished.connect(self.preview_finished)
            worker.start()
        else:
            try:
                self.display_preview(service.inspect(choice))
            except DomainError as error:
                self.preview_failed(str(error))

    def preview_loaded(self, value: object) -> None:
        self.display_preview(cast(Preview, value))

    def preview_failed(self, message: str) -> None:
        self.message.show_message(message, "error")
        self.stack.setCurrentWidget(self.error_view)
        self.source_toggle.setEnabled(bool(self.source_text))
        self.entries.setEnabled(False)
        self.views.setEnabled(False)
        self.set_controls(False)

    def preview_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def display_preview(self, preview: Preview) -> None:
        self.setWindowTitle("Aperçu — " + preview.name)
        self.source.setText(
            f"Origine : {origin_label(preview.origin)}\n"
            f"Source : {preview.source or 'Non renseignée'}\n"
            f"SHA-256 : {preview.sha256}\n\nCopie en mémoire contrôlée par SHA-256. "
            "Aucun choix ni état de validation modifié."
        )
        self.source_text = self.source.toPlainText()
        if preview.content.mesh is not None:
            mesh = preview.content.mesh
            self.stack.setCurrentWidget(self.model_view)
            self.model_view.display(mesh)
            self.views.setEnabled(True)
            self.set_controls(True)
            self.legend.setText(
                "Glisser : rotation · bouton droit : déplacement · molette : zoom. "
                f"{len(mesh.vertices)} sommets · {len(mesh.faces)} faces."
            )
            self.legend.setToolTip(
                "Projection orthographique simplifiée ; ne vérifie pas "
                "l’alignement du modèle avec le footprint."
            )
            self.message.clear()
            if mesh.warnings:
                self.message.show_message("\n".join(mesh.warnings), "warning")
                self.source.setText(
                    self.source_text + "\n\nLimites de l’aperçu\n" + "\n".join(mesh.warnings)
                )
        elif preview.content.pdf:
            self.entries.hide()
            self.page.show()
            self.legend.setToolTip(HELP["pdf"])
            self.page.setEnabled(False)
            self.stack.setCurrentWidget(self.pdf_view)
            self.legend.setText(
                "Document complet · faites défiler les pages ou utilisez le sélecteur."
            )
            self.buffer.setData(QByteArray(preview.content.pdf))
            self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.document.load(self.buffer)
        else:
            self.stack.setCurrentWidget(self.drawing_view)
            self.drawings = preview.content.drawings
            self.annotations.setVisible(preview.kind is AssetType.FOOTPRINT)
            for drawing in self.drawings:
                self.entries.addItem(f"{drawing.name} · unité {drawing.unit} · vue {drawing.style}")
            self.show_drawing()

    def set_controls(self, enabled: bool) -> None:
        for button in (self.minus, self.plus, self.fit_button):
            button.setEnabled(enabled)

    def show_drawing(self) -> None:
        index = self.entries.currentIndex()
        if not 0 <= index < len(self.drawings):
            return
        drawing = self.drawings[index]
        self.drawing_view.annotations = self.annotations.isChecked()
        self.drawing_view.display(drawing)
        self.message.clear()
        self.source.setText(
            self.source_text
            + (
                "\n\nLimites de l’aperçu\n" + "\n".join(drawing.warnings)
                if drawing.warnings
                else ""
            )
        )
        if drawing.warnings:
            summary = "\n".join(drawing.warnings[:3])
            if len(drawing.warnings) > 3:
                summary += "\nAutres limites : consultez Provenance et détails de l’aperçu."
            self.message.show_message(summary, "warning")
        elif not drawing.primitives:
            self.message.show_message(
                "Aucun élément graphique dans cette représentation.", "warning"
            )
        self.legend.setToolTip(
            HELP["footprint"] if self.kind is AssetType.FOOTPRINT else HELP["symbol"]
        )
        self.legend.setText(
            "Vue de dessus · pads dorés, pad 1 rouge · "
            "sérigraphie bleue · contour gris · courtyard violet."
            if self.kind is AssetType.FOOTPRINT
            else "Broches bleues · contours sombres · "
            "noms et numéros affichés pour l’inspection, même si masqués dans KiCad."
        )
        QTimer.singleShot(0, self.drawing_view.fit)

    def pdf_status(self, status: QPdfDocument.Status) -> None:
        ready = status == QPdfDocument.Status.Ready
        self.set_controls(ready)
        self.page.setEnabled(ready)
        if ready:
            self.page.setRange(1, self.document.pageCount())
            self.page.setSuffix(f" / {self.document.pageCount()}")
            self.message.clear()
        elif status == QPdfDocument.Status.Error:
            self.message.show_message(
                "PDF illisible, protégé ou non supporté par le viewer. Le fichier reste conservé.",
                "error",
            )

    def page_changed(self, page: int) -> None:
        self.page.blockSignals(True)
        self.page.setValue(page + 1)
        self.page.blockSignals(False)

    def go_page(self, page: int) -> None:
        if self.document.status() == QPdfDocument.Status.Ready:
            self.pdf_view.pageNavigator().jump(page - 1, QPointF(), self.pdf_view.zoomFactor())

    def zoom(self, factor: float) -> None:
        if self.stack.currentWidget() is self.pdf_view:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.pdf_view.setZoomFactor(max(0.1, min(8, self.pdf_view.zoomFactor() * factor)))
        elif self.stack.currentWidget() is self.model_view:
            self.model_view.zoom(factor)
        else:
            self.drawing_view.zoom(factor)

    def fit(self) -> None:
        if self.stack.currentWidget() is self.pdf_view:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        elif self.stack.currentWidget() is self.model_view:
            self.model_view.fit()
        else:
            self.drawing_view.fit()

    def toggle_size(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.expand.setText("Agrandir la fenêtre")
        else:
            self.showMaximized()
            self.expand.setText("Taille normale")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None:
            self.message.show_message("Attendre la fin de la préparation 3D avant de fermer.")
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self.worker is not None:
            self.message.show_message("Attendre la fin de la préparation 3D avant de fermer.")
            return
        super().reject()


class PreviewWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: Previews, choice: ResourceChoice, parent: QWidget) -> None:
        super().__init__(parent)
        self.service, self.choice = service, choice

    def run(self) -> None:
        try:
            self.loaded.emit(self.service.inspect(self.choice))
        except DomainError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Impossible de préparer ce modèle 3D. Le fichier reste conservé.")
