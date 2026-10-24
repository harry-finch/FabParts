"""Version creation and historical integrity/reconstruction in the shared shell."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from PySide6.QtCore import QEventLoop, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kipartmanager.application.bundles import Bundles
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.publications import Publications
from kipartmanager.domain.entities import Collection, DomainError
from kipartmanager.domain.publication import Publication
from kipartmanager.ui.components import (
    DetailText,
    EmptyState,
    MessageBanner,
    PageHeader,
    PageLayout,
    ScrollPanel,
    SectionCard,
    StatusBadge,
    label,
)
from kipartmanager.ui.context_help import HELP


class PublicationsPanel(QWidget):
    imported = Signal()

    def __init__(
        self, catalogue: Catalogue, service: Publications, bundles: Bundles | None = None
    ) -> None:
        super().__init__()
        self.catalogue, self.service, self.bundles = catalogue, service, bundles
        self.records: tuple[Publication, ...] = ()
        layout = PageLayout(self)
        self.publish_button = QPushButton("Publier une version")
        self.publish_button.clicked.connect(self.publish)
        layout.addWidget(
            PageHeader(
                "Publications",
                HELP["publication"],
                self.publish_button,
            )
        )
        controls = QHBoxLayout()
        self.collections = QComboBox()
        self.collections.setAccessibleName("Bibliothèque à publier ou historique à filtrer")
        self.collections.currentIndexChanged.connect(self.reload_history)
        self.version = QSpinBox()
        self.version.setRange(1, 999999)
        self.version.setAccessibleName("Numéro de la nouvelle version")
        collection_fields = QVBoxLayout()
        collection_fields.addWidget(label("Bibliothèque"))
        collection_fields.addWidget(self.collections)
        version_fields = QVBoxLayout()
        version_fields.addWidget(label("Nouvelle version"))
        version_fields.addWidget(self.version)
        controls.addLayout(collection_fields, 3)
        controls.addLayout(version_fields, 1)
        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(controls)
        layout.addWidget(label("Validez la bibliothèque et acceptez ses WARNING avant de publier."))
        if bundles:
            transfer = QHBoxLayout()
            self.import_button = QPushButton("Importer un .kiparts…")
            self.import_button.clicked.connect(self.choose_import)
            transfer.addWidget(self.import_button)
            transfer.addWidget(label("Transférer une version complète, hors ligne."), 1)
            layout.addLayout(transfer)
            self.import_card = SectionCard("Import à examiner")
            self.import_summary = DetailText()
            self.import_card.body.addWidget(self.import_summary, 1)
            self.confirm_import = QPushButton("Importer sans remplacer")
            self.confirm_import.clicked.connect(self.import_archive)
            import_actions = QHBoxLayout()
            close_preview = QPushButton("Fermer l’aperçu")
            close_preview.clicked.connect(self.close_import)
            import_actions.addWidget(close_preview)
            import_actions.addWidget(self.confirm_import, 1)
            self.import_card.body.addLayout(import_actions)
            self.import_card.hide()
            layout.addWidget(self.import_card, 1)
        self.import_source = ""
        split = QSplitter()
        self.history_split = split
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self.select)
        self.empty = EmptyState(
            "Aucune publication",
            "Choisissez une bibliothèque qualifiée, puis publiez sa première version.",
        )
        self.history = QStackedWidget()
        self.history.addWidget(self.items)
        self.history.addWidget(self.empty)
        split.addWidget(self.history)
        card = SectionCard("Version sélectionnée")
        self.badge = StatusBadge()
        card.body.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = DetailText()
        card.body.addWidget(self.details, 1)
        self.export_button = QPushButton("Exporter cette version en .kiparts…")
        self.export_button.clicked.connect(self.export_archive)
        self.export_button.setVisible(bundles is not None)
        card.body.addWidget(self.export_button)
        self.verify_button = QPushButton("Vérifier les hashes")
        self.verify_button.clicked.connect(self.verify)
        card.body.addWidget(self.verify_button)
        card.body.addWidget(label("Reconstruire dans un nouveau dossier"))
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("Destination de la copie KiCad")
        card.body.addWidget(self.destination)
        self.choose_button = QPushButton("Choisir le dossier parent")
        self.choose_button.clicked.connect(self.choose)
        card.body.addWidget(self.choose_button)
        self.rebuild_button = QPushButton("Reconstruire cette version")
        self.rebuild_button.clicked.connect(self.rebuild)
        card.body.addWidget(self.rebuild_button)
        card.setMinimumWidth(290)
        self.details.setMinimumHeight(140)
        scroll = ScrollPanel(card)
        scroll.setMinimumWidth(310)
        split.addWidget(scroll)
        split.setSizes([600, 350])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        self.refresh()

    def refresh(self) -> None:
        selected = self.collections.currentData()
        self.collections.blockSignals(True)
        self.collections.clear()
        self.collections.addItem("Toutes les publications", None)
        for collection in self.catalogue.list_entities(Collection):
            self.collections.addItem(collection.name, str(collection.id))
        index = self.collections.findData(selected)
        self.collections.setCurrentIndex(max(0, index))
        self.collections.blockSignals(False)
        self.reload_history()

    def reload_history(self) -> None:
        self.message.clear()
        self.records = ()
        self.items.clear()
        identity = self.collections.currentData()
        self.publish_button.setEnabled(identity is not None)
        self.version.setEnabled(identity is not None)
        try:
            self.records = self.service.list_publications(UUID(identity) if identity else None)
            for publication in self.records:
                self.items.addItem(
                    f"{publication.collection_name} · v{publication.version}\n"
                    f"{publication.created_at[:19].replace('T', ' ')} UTC · manifest engagé"
                )
            self.version.setValue(
                min(999999, max((p.version for p in self.records), default=0) + 1)
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")
        self.history.setCurrentIndex(0 if self.records else 1)
        self.select()

    def selected(self) -> Publication | None:
        row = self.items.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def select(self) -> None:
        self.message.clear()
        publication = self.selected()
        self.export_button.setEnabled(publication is not None)
        self.verify_button.setEnabled(publication is not None)
        self.choose_button.setEnabled(publication is not None)
        self.destination.setEnabled(publication is not None)
        self.rebuild_button.setEnabled(publication is not None)
        self.badge.set_status("PUBLISHED" if publication else "")
        self.details.setText(
            f"{publication.collection_name} — version {publication.version}\n\n"
            f"Bibliothèque\n{publication.collection_id}\n\nCréée\n{publication.created_at}\n\n"
            f"Manifest SHA-256\n{publication.manifest_sha256}\n\n"
            f"Qualification M5\n{publication.fingerprint}\n\n"
            "Manifest engagé ; intégrité des fichiers à vérifier.\n"
            "La reconstruction utilise les sources figées, sans relire le catalogue courant."
            if publication
            else "Sélectionnez une version pour vérifier son intégrité ou la reconstruire."
        )

    def publish(self) -> None:
        identity = self.collections.currentData()
        if not identity:
            return
        try:
            collection = self.catalogue.require(Collection, UUID(identity))
            publication = self.service.publish(collection, self.version.value())
            self.reload_history()
            self.items.setCurrentRow(self.records.index(publication))
            self.message.show_message(
                "Version engagée. Les versions précédentes sont conservées.", "success"
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def verify(self) -> None:
        publication = self.selected()
        if publication:
            try:
                self.service.verify(publication)
                self.badge.set_status("PASS")
                self.details.setText(
                    self.details.toPlainText().replace(
                        "Manifest engagé ; intégrité des fichiers à vérifier.",
                        "Manifest, sources et artefacts vérifiés à cet instant.",
                    )
                )
                self.message.show_message("Manifest, dépendances et artefacts vérifiés.", "success")
            except DomainError as error:
                self.badge.set_status("ERROR")
                self.message.show_message(str(error), "error")

    def choose(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Dossier parent de reconstruction")
        publication = self.selected()
        if parent and publication:
            self.destination.setText(
                parent.rstrip("/\\")
                + f"/KiPart-{publication.collection_id.hex}-v{publication.version}"
            )

    def rebuild(self) -> None:
        publication = self.selected()
        if publication:
            if not self.destination.text().strip():
                self.message.show_message("Choisissez un nouveau dossier de destination.")
                return
            try:
                result = self.service.rebuild(publication, self.destination.text().strip())
                self.message.show_message(
                    f"Version {publication.version} reconstruite à l'identique : "
                    f"{len(result.files)} fichiers.\n{result.destination}",
                    "success",
                )
            except DomainError as error:
                self.message.show_message(str(error), "error")

    def export_archive(self) -> None:
        publication = self.selected()
        if not publication or not self.bundles:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la version portable",
            f"KiPart-{publication.collection_id.hex}-v{publication.version}.kiparts",
            "Bibliothèque FabParts (*.kiparts)",
        )
        if not destination:
            return
        try:
            with self.transfer_busy("Export et vérification de l’archive…"):
                self.bundles.export(publication, destination)
            self.message.show_message("Archive complète exportée : " + destination, "success")
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def choose_import(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Examiner une bibliothèque portable", "", "Bibliothèque FabParts (*.kiparts)"
        )
        if source:
            self.inspect_archive(source)

    def inspect_archive(self, source: str) -> None:
        if not self.bundles:
            return
        self.import_source = ""
        self.import_card.hide()
        self.history_split.show()
        try:
            with self.transfer_busy("Vérification de l’archive et des conflits…"):
                preview = self.bundles.inspect(source)
            self.import_source = source
            self.import_summary.setText(
                f"{preview.publication.collection_name} · v{preview.publication.version}\n"
                f"{preview.parts} composant(s) · {preview.packages} package(s) · "
                f"{preview.assets} ressources\n"
                + (
                    "Conflits — aucun remplacement autorisé :\n" + "\n".join(preview.conflicts)
                    if preview.conflicts
                    else "Aucun conflit. Les entrées identiques seront réutilisées.\n"
                    "Les stocks restent locaux ; la qualification courante sera à recalculer."
                )
            )
            self.confirm_import.setEnabled(preview.can_import)
            self.import_card.show()
            self.history_split.hide()
            self.message.show_message(
                "Archive vérifiée. Examinez le contenu avant l'import."
                if preview.can_import
                else "Import bloqué par des conflits locaux.",
                "info" if preview.can_import else "error",
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def import_archive(self) -> None:
        if not self.import_source or not self.bundles:
            return
        try:
            with self.transfer_busy("Import de la bibliothèque…"):
                preview = self.bundles.import_bundle(self.import_source)
            self.import_source = ""
            self.import_card.hide()
            self.history_split.show()
            self.imported.emit()
            self.refresh()
            self.collections.setCurrentIndex(
                self.collections.findData(str(preview.publication.collection_id))
            )
            if preview.publication in self.records:
                self.items.setCurrentRow(self.records.index(preview.publication))
            self.message.show_message(
                "Bibliothèque importée et version historique vérifiée. "
                "Validez localement les composants avant une nouvelle publication.",
                "success",
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def close_import(self) -> None:
        self.import_source = ""
        self.import_card.hide()
        self.history_split.show()
        self.message.clear()

    @contextmanager
    def transfer_busy(self, message: str) -> Iterator[None]:
        self.message.show_message(message)
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            yield
        finally:
            QApplication.restoreOverrideCursor()
            self.setEnabled(True)
