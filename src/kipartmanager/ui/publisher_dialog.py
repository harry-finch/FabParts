"""Explicit construction of a new copy-mode output folder for a collection."""

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.domain.build import library_name
from kipartmanager.domain.entities import Collection, DomainError
from kipartmanager.ui.components import MessageBanner, PageHeader, PageLayout, primary


class PublisherDialog(QDialog):
    def __init__(
        self, publisher: LocalPublisher, collection: Collection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.publisher, self.collection = publisher, collection
        self.setWindowTitle(f"Construire une bibliothèque KiCad — {collection.name}")
        self.resize(800, 600)
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                "Construire pour KiCad",
                f"Collection : {collection.name} — copie autonome vers un nouveau dossier.",
            )
        )
        explanation = QLabel(
            "Copie autonome des ressources choisies, avec tables de projet et liens portables. "
            "La collection doit avoir un rapport M5 actuel, avec WARNING acceptés. "
            "Choisir un nouveau dossier de sortie ; une destination existante est refusée."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("Chemin du nouveau dossier de sortie")
        layout.addWidget(self.destination)
        choose = QPushButton("Choisir le dossier parent")
        choose.clicked.connect(self.choose)
        layout.addWidget(choose)
        self.build_button = QPushButton("Construire la bibliothèque")
        self.build_button.clicked.connect(self.build)
        layout.addWidget(primary(self.build_button))
        self.status = MessageBanner()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def choose(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier parent de la sortie KiCad")
        if directory:
            self.destination.setText(
                directory.rstrip("/\\")
                + "/"
                + library_name(self.collection.name, self.collection.id)
            )

    def build(self) -> None:
        if not self.destination.text().strip():
            self.status.setText("Choisir un nouveau dossier de sortie.")
            return
        try:
            result = self.publisher.build(self.collection, self.destination.text().strip())
            self.status.setText(
                f"Construction terminée : {result.symbols} composants, "
                f"{result.footprints} footprints, {len(result.files)} fichiers.\n"
                f"{result.destination}\nBibliothèque : {result.library}\n"
                "Consulter UTILISATION.txt pour ajouter les bibliothèques au projet KiCad."
            )
        except DomainError as error:
            self.status.show_message(str(error), "error")
