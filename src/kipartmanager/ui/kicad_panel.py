"""Configuration, background rebuilding and browsing of external references."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.previews import Previews
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.kicad import IndexReport, KiCadReference, LibraryRoots
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ui.components import (
    DetailText,
    EmptyState,
    MessageBanner,
    PageHeader,
    PageLayout,
    SearchBar,
    SectionCard,
)
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.preview_dialog import PreviewDialog
from kipartmanager.ui.theme import M


class RebuildWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: KiCadLibraries, parent: QWidget) -> None:
        super().__init__(parent)
        self.service = service

    def run(self) -> None:
        try:
            self.completed.emit(self.service.rebuild())
        except DomainError as error:
            self.failed.emit(str(error))


class KiCadPanel(QWidget):
    def __init__(self, service: KiCadLibraries, *, previews: Previews | None = None) -> None:
        super().__init__()
        self.service = service
        self.previews = previews
        self.worker: RebuildWorker | None = None
        self.references: list[KiCadReference] = []
        layout = PageLayout(self)
        self.discover_button = QPushButton("Découvrir les dossiers installés")
        self.save_button = QPushButton("Enregistrer la configuration")
        self.rebuild_button = QPushButton("Réindexer")
        self.discover_button.clicked.connect(self.discover)
        self.save_button.clicked.connect(self.configure)
        self.rebuild_button.clicked.connect(self.rebuild)
        layout.addWidget(
            PageHeader(
                "KiCad local",
                HELP["official"],
                self.rebuild_button,
            )
        )
        toggle = QPushButton("Dossiers des bibliothèques")
        self.config_toggle = toggle
        toggle.setCheckable(True)
        layout.addWidget(toggle)
        config = SectionCard("Sources configurées")
        form = QFormLayout()
        form.setVerticalSpacing(M)
        self.paths = [QLineEdit() for _ in range(3)]
        for title, field in zip(("Symboles", "Footprints", "Modèles 3D"), self.paths, strict=True):
            form.addRow(title, field)
        config.body.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addWidget(self.discover_button)
        buttons.addWidget(self.save_button)
        config.body.addLayout(buttons)
        layout.addWidget(config)
        config.hide()
        toggle.toggled.connect(config.setVisible)
        controls = QHBoxLayout()
        self.query = SearchBar("Nom, bibliothèque, description ou mots-clés")
        self.kind = QComboBox()
        self.kind.addItem("Tous les types", "")
        for kind in (AssetType.SYMBOL, AssetType.FOOTPRINT, AssetType.MODEL_3D):
            self.kind.addItem(kind.value, kind.value)
        search_button = QPushButton("Rechercher")
        search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        controls.addWidget(self.query, 1)
        controls.addWidget(self.kind)
        controls.addWidget(search_button)
        layout.addLayout(controls)
        self.empty = EmptyState(
            "Explorez vos bibliothèques locales",
            "Configurez les dossiers, réindexez puis recherchez une ressource. "
            "Les sources restent inchangées.",
        )
        splitter = QSplitter()
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self.show_details)
        self.results = QStackedWidget()
        self.results.addWidget(self.items)
        self.results.addWidget(self.empty)
        self.results.setCurrentIndex(1)
        splitter.addWidget(self.results)
        card = SectionCard("Ressource sélectionnée")
        self.details = DetailText(
            "Sélectionnez un résultat pour consulter provenance, version et empreinte."
        )
        self.details.setMinimumWidth(0)
        card.body.addWidget(self.details)
        self.preview_button = QPushButton("Inspecter la ressource…")
        self.preview_button.setVisible(previews is not None)
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.inspect_resource)
        card.body.addWidget(self.preview_button)
        splitter.addWidget(card)
        splitter.setSizes([650, 300])
        layout.addWidget(splitter, 1)
        self.status = MessageBanner()
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.issues = QListWidget()
        self.issues.setMaximumHeight(100)
        self.issues.hide()
        layout.addWidget(self.issues)
        try:
            self.set_roots(service.configuration())
            self.show_report(service.report())
        except DomainError as error:
            self.status.show_message(str(error), "error")

    def inspect_resource(self) -> None:
        index = self.items.currentRow()
        if self.previews is not None and 0 <= index < len(self.references):
            ref = self.references[index]
            PreviewDialog(self.previews, ResourceChoice(ref.asset_type, reference=ref), self).show()

    def show_details(self) -> None:
        index = self.items.currentRow()
        self.preview_button.setEnabled(0 <= index < len(self.references))
        self.preview_button.setToolTip("Lecture seule ; aucun import. STEP : FreeCAD local requis.")
        if 0 <= index < len(self.references):
            ref = self.references[index]
            self.details.setText(
                f"{ref.name}\n\n{ref.description or 'Sans description'}\n\n"
                f"Bibliothèque : {ref.library}\nType : {ref.asset_type.value}\n"
                f"Origine : {ref.origin.value}\nVersion : {ref.format_version or '—'}\n"
                f"Indexation : disponible dans le cache local\nValidation : UNCHECKED"
                f"\n\nSource relative\n{ref.relative_path}\n\nSHA-256\n{ref.sha256}"
            )
        else:
            self.details.setText("Sélectionnez un résultat pour consulter ses informations.")

    def set_roots(self, roots: LibraryRoots) -> None:
        for field, value in zip(
            self.paths, (roots.symbols, roots.footprints, roots.models), strict=True
        ):
            field.setText(value)

    def discover(self) -> None:
        roots = self.service.discover()
        self.set_roots(roots)
        self.status.setText(
            "Dossiers proposés ; enregistrer puis reconstruire."
            if any((roots.symbols, roots.footprints, roots.models))
            else "Aucune installation détectée ; saisir les dossiers manuellement."
        )

    def configure(self) -> None:
        try:
            self.service.configure(LibraryRoots(*(field.text().strip() for field in self.paths)))
            self.set_roots(self.service.configuration())
            self.show_report(self.service.report())
        except DomainError as error:
            self.status.show_message(str(error), "error")

    def rebuild(self) -> None:
        if self.worker is not None:
            return
        try:
            # Always persist the paths shown before scanning; invalid paths leave old cache intact.
            self.service.configure(LibraryRoots(*(field.text().strip() for field in self.paths)))
        except DomainError as error:
            self.status.show_message(str(error), "error")
            return
        self.status.setText("Reconstruction locale en cours…")
        self.busy(True)
        worker = RebuildWorker(self.service, self)
        self.worker = worker
        worker.completed.connect(self.show_report)
        worker.failed.connect(lambda text: self.status.show_message(text, "error"))
        worker.finished.connect(self.finished)
        worker.start()

    def busy(self, value: bool) -> None:
        self.progress.setVisible(value)
        for widget in (*self.paths, self.discover_button, self.save_button, self.rebuild_button):
            widget.setEnabled(not value)

    def finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.busy(False)

    def show_report(self, report: IndexReport) -> None:
        self.status.setText(
            f"{report.count} références indexées ; {len(report.issues)} signalements."
        )
        self.issues.clear()
        self.issues.setVisible(bool(report.issues))
        for issue in report.issues:
            self.issues.addItem(f"{issue.source} : {issue.message}")

    def search(self) -> None:
        try:
            kind = self.kind.currentData()
            self.references = self.service.search(
                self.query.text(), AssetType(kind) if kind else None
            )
            self.items.clear()
            for ref in self.references:
                self.items.addItem(
                    f"{ref.name}\n{ref.asset_type.value} · {ref.library}\n"
                    "Official KiCad · Indexée · Validation UNCHECKED"
                )
            self.results.setCurrentIndex(0 if self.references else 1)
            if not self.references:
                self.empty.title.setText("Aucun résultat local")
                self.empty.description.setText(
                    "Essayez un autre nom ou vérifiez la configuration et l'index."
                )
            self.show_details()
            self.status.setText(f"{len(self.references)} résultats (limite 200) ; cache local.")
        except DomainError as error:
            self.status.show_message(str(error), "error")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None:
            event.ignore()
        else:
            super().closeEvent(event)
