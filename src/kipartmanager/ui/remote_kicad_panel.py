"""Explicit opt-in remote search and download; never selects or replaces resources."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
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

from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.remote_kicad import (
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteSearch,
)
from kipartmanager.ui.components import (
    DetailText,
    EmptyState,
    MessageBanner,
    PageHeader,
    PageLayout,
    SearchBar,
    SectionCard,
    primary,
)
from kipartmanager.ui.theme import M


class RemoteWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: RemoteLibraries,
        parent: QWidget,
        *,
        kind: AssetType,
        library: str,
        query: str,
        candidate: RemoteCandidate | None = None,
    ) -> None:
        super().__init__(parent)
        self.service, self.kind, self.library, self.query = service, kind, library, query
        self.candidate = candidate

    def run(self) -> None:
        try:
            result = (
                self.service.download(self.candidate)
                if self.candidate is not None
                else self.service.search(self.kind, self.library, self.query)
            )
            self.completed.emit(result)
        except DomainError as error:
            self.failed.emit(str(error))
        except Exception:
            # A faulty optional adapter must not leave the UI busy or break local workflows.
            self.failed.emit(
                "Erreur inattendue de l’adaptateur distant ; ressources locales conservées."
            )


class RemoteKiCadPanel(QWidget):
    imported = Signal()

    def __init__(self, service: RemoteLibraries) -> None:
        super().__init__()
        self.service = service
        self.worker: RemoteWorker | None = None
        self.candidates: tuple[RemoteCandidate, ...] = ()
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                "KiCad officiel distant",
                "Source optionnelle GitLab · recherche explicite · aucun remplacement automatique.",
            )
        )
        self.config_toggle = QPushButton("Configurer l’accès distant")
        self.config_toggle.setCheckable(True)
        layout.addWidget(self.config_toggle)
        config = SectionCard("Accès distant")
        self.config_card = config
        self.config_toggle.toggled.connect(config.setVisible)
        self.enabled = QCheckBox("Autoriser les recherches et téléchargements officiels GitLab")
        config.body.addWidget(self.enabled)
        form = QFormLayout()
        form.setVerticalSpacing(M)
        self.revision = QLineEdit("9.0.0")
        self.revision.setToolTip("Tag ou branche résolu en commit immuable à chaque recherche.")
        form.addRow("Révision officielle", self.revision)
        config.body.addLayout(form)
        self.save_button = QPushButton("Enregistrer la configuration")
        self.save_button.clicked.connect(self.configure)
        config.body.addWidget(self.save_button)
        layout.addWidget(config)
        config.hide()
        form = QFormLayout()
        self.kind = QComboBox()
        for kind in (AssetType.SYMBOL, AssetType.FOOTPRINT, AssetType.MODEL_3D):
            self.kind.addItem(kind.value, kind.value)
        self.library = QLineEdit()
        self.library.setPlaceholderText("Device, Resistor_SMD… (sans extension)")
        form.addRow("Type de ressource", self.kind)
        form.addRow("Bibliothèque précise *", self.library)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.query = SearchBar("Filtrer les noms ; symboles : description et mots-clés aussi")
        self.search_button = QPushButton("Rechercher en ligne")
        self.search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        controls.addWidget(self.query, 1)
        controls.addWidget(primary(self.search_button))
        layout.addLayout(controls)
        self.items = QListWidget()
        self.items.setAccessibleName("Candidats officiels distants, non sélectionnés")
        self.items.currentRowChanged.connect(self.show_candidate)
        self.results = QStackedWidget()
        self.results.addWidget(self.items)
        self.empty = EmptyState(
            "Recherche distante désactivée",
            "Les ressources locales restent disponibles sans Internet.",
        )
        self.results.addWidget(self.empty)
        self.results.setCurrentIndex(1)
        self.details = DetailText("Recherchez puis comparez un candidat distant.")
        card = SectionCard("Candidat distant")
        card.body.addWidget(self.details, 1)
        self.import_button = QPushButton("Télécharger comme nouvel asset")
        self.import_button.clicked.connect(self.download)
        card.body.addWidget(self.import_button)
        split = QSplitter()
        split.addWidget(self.results)
        split.addWidget(card)
        split.setSizes([500, 350])
        layout.addWidget(split, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        for field in (self.kind,):
            field.currentIndexChanged.connect(self.clear_results)
        self.library.textChanged.connect(self.clear_results)
        self.query.textChanged.connect(self.clear_results)
        self.enabled.toggled.connect(self.clear_results)
        self.revision.textChanged.connect(self.clear_results)
        try:
            config_value = service.configuration()
            self.enabled.setChecked(config_value.enabled)
            self.revision.setText(config_value.revision)
            self.config_label(config_value)
            if config_value.enabled:
                self.empty.title.setText("Aucune recherche distante lancée")
                self.empty.description.setText(
                    "Saisissez une bibliothèque précise puis recherchez en ligne."
                )
        except DomainError as error:
            self.message.show_message(str(error), "error")
        self.show_candidate()

    def clear_results(self) -> None:
        self.candidates = ()
        self.items.clear()
        self.results.setCurrentIndex(1)
        self.empty.title.setText("Aucune recherche distante lancée")
        self.empty.description.setText(
            "Enregistrez l’accès distant, puis recherchez dans une bibliothèque précise."
        )
        self.message.clear()
        self.show_candidate()

    def config_label(self, config: RemoteConfiguration) -> None:
        state = "activé" if config.enabled else "désactivé"
        self.config_toggle.setText(f"Accès distant : {state} · {config.revision} — configurer")

    def configure(self) -> None:
        try:
            self.service.configure(
                RemoteConfiguration(self.enabled.isChecked(), self.revision.text().strip())
            )
            self.config_label(self.service.configuration())
            self.config_toggle.setChecked(False)
            self.clear_results()
            self.message.show_message(
                "Configuration enregistrée ; aucun accès réseau effectué.", "success"
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def saved_configuration(self) -> None:
        expected = RemoteConfiguration(self.enabled.isChecked(), self.revision.text().strip())
        if self.service.configuration() != expected:
            raise DomainError(
                "Enregistrer la configuration affichée avant de rechercher ou télécharger."
            )
        self.service.require_enabled()

    def show_candidate(self) -> None:
        row = self.items.currentRow()
        candidate = self.candidates[row] if 0 <= row < len(self.candidates) else None
        self.import_button.setEnabled(candidate is not None and self.worker is None)
        self.details.setText(
            f"{candidate.identifier}\nOfficial KiCad · DISTANT · UNCHECKED\n\n"
            f"{candidate.description}\n\nRévision : {candidate.revision}\n"
            f"Commit : {candidate.commit}\n\nSource\n{candidate.source}\n\n"
            f"SHA-256 : {candidate.sha256 or 'calculé après téléchargement'}\n"
            "Import dans le catalogue uniquement ; choisir ensuite dans les ressources locales."
            if candidate
            else "Recherchez puis comparez un candidat distant."
        )

    def search(self) -> None:
        self.start(None)

    def download(self) -> None:
        row = self.items.currentRow()
        if 0 <= row < len(self.candidates):
            self.start(self.candidates[row])

    def start(self, candidate: RemoteCandidate | None) -> None:
        if self.worker is not None:
            return
        try:
            self.saved_configuration()
        except DomainError as error:
            self.message.show_message(str(error), "warning")
            return
        if candidate is None:
            self.clear_results()
        self.message.show_message(
            "Téléchargement en cours…" if candidate else "Recherche distante en cours…"
        )
        worker = RemoteWorker(
            self.service,
            self,
            kind=AssetType(self.kind.currentData()),
            library=self.library.text(),
            query=self.query.text(),
            candidate=candidate,
        )
        self.worker = worker
        worker.completed.connect(self.completed)
        worker.failed.connect(lambda message: self.message.show_message(message, "error"))
        worker.finished.connect(self.finished)
        self.busy(True)
        worker.start()

    def completed(self, result: RemoteSearch | RemoteDownload) -> None:
        if isinstance(result, RemoteSearch):
            self.candidates = result.candidates
            self.items.clear()
            for candidate in self.candidates:
                self.items.addItem(
                    f"{candidate.name}\nOfficial KiCad · DISTANT · {candidate.revision}"
                )
            self.results.setCurrentIndex(0 if self.candidates else 1)
            self.empty.title.setText("Aucun candidat distant")
            self.empty.description.setText("Essayez un autre filtre ou une autre bibliothèque.")
            self.message.show_message(
                f"{len(self.candidates)} candidats ; aucun choix automatique. "
                + " ".join(result.notices)
            )
        else:
            try:
                asset = self.service.import_download(result)
                self.message.show_message(
                    f"{asset.name} importé · UNCHECKED. "
                    "Choisissez-le explicitement dans les ressources locales.",
                    "success",
                )
                self.imported.emit()
            except DomainError as error:
                self.message.show_message(str(error), "error")

    def busy(self, value: bool) -> None:
        self.progress.setVisible(value)
        for widget in (
            self.config_toggle,
            self.enabled,
            self.revision,
            self.save_button,
            self.kind,
            self.library,
            self.query,
            self.search_button,
            self.items,
        ):
            widget.setEnabled(not value)
        self.show_candidate()

    def finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.busy(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None:
            event.ignore()
        else:
            super().closeEvent(event)
