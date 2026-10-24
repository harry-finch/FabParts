"""Explicit sharing and structured suggestions within Documentation, not a chatbot."""

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from kipartmanager.application.assistance import Assistance
from kipartmanager.domain.assistance import (
    AssistanceBackend,
    AssistanceConfiguration,
    AssistanceRequest,
)
from kipartmanager.domain.documentation import Identification, MetadataProposal
from kipartmanager.domain.entities import DomainError
from kipartmanager.ui.components import (
    DetailText,
    MessageBanner,
    PageLayout,
    ScrollPanel,
    label,
    primary,
    quiet,
)


class AssistanceWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: Assistance,
        request: AssistanceRequest,
        config: AssistanceConfiguration,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.service, self.request, self.config = service, request, config

    def run(self) -> None:
        try:
            self.completed.emit(self.service.suggest(self.request, self.config, consent=True))
        except DomainError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Fournisseur indisponible ; données locales conservées.")


class AssistancePanel(QWidget):
    busy_changed = Signal(bool)

    def __init__(
        self,
        service: Assistance,
        current: Callable[[], Identification],
        review: Callable[[MetadataProposal], None],
    ) -> None:
        super().__init__()
        self.service, self.current, self.review = service, current, review
        self.worker: AssistanceWorker | None = None
        self.expected: Identification | None = None
        self.request: AssistanceRequest | None = None
        layout = PageLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)
        body = QWidget()
        fields = PageLayout(body)
        fields.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(ScrollPanel(body), 1)
        fields.addWidget(
            label(
                "Suggestions à vérifier. Aucun fichier, historique ou stock n’est "
                "envoyé automatiquement."
            )
        )
        self.config_toggle = quiet(QPushButton("Configurer le fournisseur IA · facultatif"))
        self.config_toggle.setCheckable(True)
        fields.addWidget(self.config_toggle)
        self.config_widget = QWidget()
        form = QFormLayout(self.config_widget)
        self.enabled = QCheckBox("Activer l’assistance IA")
        self.backend = QComboBox()
        self.backend.addItem("Gemini", AssistanceBackend.GEMINI.value)
        self.backend.addItem("API compatible OpenAI", AssistanceBackend.CHAT.value)
        self.backend.addItem("Ollama sur ce poste", AssistanceBackend.OLLAMA.value)
        self.endpoint, self.model = QLineEdit(), QLineEdit()
        self.endpoint.setPlaceholderText("URL finale du service")
        self.model.setPlaceholderText("Modèle disponible sur votre compte ou installé localement")
        self.save_button = QPushButton("Enregistrer la configuration")
        self.save_button.clicked.connect(self.configure)
        self.gemini_button = QPushButton("Préremplir l’URL Gemini")
        self.gemini_button.clicked.connect(self.gemini)
        self.ollama_button = QPushButton("Préremplir Ollama local")
        self.ollama_button.clicked.connect(self.ollama)
        for title, widget in (
            ("Accès", self.enabled),
            ("Fournisseur", self.backend),
            ("URL *", self.endpoint),
            ("Modèle *", self.model),
            ("", self.gemini_button),
            ("", self.ollama_button),
            ("", self.save_button),
        ):
            form.addRow(title, widget)
        form.addRow(
            label(
                "Secret distant : GEMINI_API_KEY pour Gemini, KIPART_AI_API_KEY "
                "ailleurs. Aucun secret saisi ici."
            )
        )
        fields.addWidget(self.config_widget)
        self.config_widget.hide()
        self.config_toggle.toggled.connect(self.config_widget.setVisible)
        self.state = label("")
        fields.addWidget(self.state)
        fields.addWidget(
            label(
                "Contexte à analyser * · saisir ou coller un extrait utile, "
                "maximum 16 000 caractères"
            )
        )
        self.context = QTextEdit()
        self.context.setAcceptRichText(False)
        self.context.setMinimumHeight(96)
        self.context.setMaximumHeight(120)
        fields.addWidget(self.context)
        self.include_values = QCheckBox("Inclure les quatre champs d’identification enregistrés")
        fields.addWidget(self.include_values)
        self.preview_button = QPushButton("Relire les données à envoyer")
        self.preview_button.clicked.connect(self.prepare)
        fields.addWidget(self.preview_button)
        self.payload = DetailText("Préparez l’envoi pour inspecter son contenu et sa destination.")
        self.payload.setMinimumHeight(110)
        self.payload.setMaximumHeight(150)
        fields.addWidget(self.payload)
        self.consent = QCheckBox("J’autorise cette requête vers la destination affichée")
        layout.addWidget(self.consent)
        self.send_button = primary(QPushButton("Demander des suggestions à relire"))
        self.send_button.clicked.connect(self.send)
        layout.addWidget(self.send_button)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        for editor in (self.context, self.endpoint, self.model):
            editor.textChanged.connect(self.invalidate)
        self.backend.currentIndexChanged.connect(self.invalidate)
        self.enabled.toggled.connect(self.invalidate)
        self.include_values.toggled.connect(self.invalidate)
        self.consent.toggled.connect(
            lambda checked: self.send_button.setEnabled(
                checked and self.request is not None and self.worker is None
            )
        )
        try:
            config = service.configuration()
            self.enabled.setChecked(config.enabled)
            self.endpoint.setText(config.endpoint)
            self.model.setText(config.model)
            self.backend.setCurrentIndex(self.backend.findData(config.backend.value))
            self.update_state()
        except DomainError as error:
            self.state.setText(str(error))
        self.invalidate()

    def gemini(self) -> None:
        self.backend.setCurrentIndex(0)
        self.endpoint.setText("https://generativelanguage.googleapis.com/v1beta")

    def ollama(self) -> None:
        self.backend.setCurrentIndex(2)
        self.endpoint.setText("http://127.0.0.1:11434/api/chat")

    def displayed_config(self) -> AssistanceConfiguration:
        return AssistanceConfiguration(
            self.enabled.isChecked(),
            self.endpoint.text().strip(),
            self.model.text().strip(),
            AssistanceBackend(self.backend.currentData()),
        )

    def update_state(self) -> None:
        config = self.service.configuration()
        self.state.setText(
            "Désactivé · identification locale disponible."
            if not config.enabled
            else f"Destination : {config.destination}\nModèle demandé : {config.model} · "
            + ("Ollama local" if config.backend is AssistanceBackend.OLLAMA else "service distant")
        )

    def configure(self) -> None:
        try:
            self.service.configure(self.displayed_config())
            self.update_state()
            self.invalidate()
            self.message.show_message(
                "Configuration enregistrée ; aucune requête lancée.", "success"
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def invalidate(self) -> None:
        self.request, self.expected = None, None
        self.consent.setChecked(False)
        self.send_button.setEnabled(False)
        self.payload.setText("Préparez l’envoi pour inspecter son contenu et sa destination.")
        self.message.clear()

    def prepare(self) -> None:
        self.invalidate()
        try:
            config = self.service.configuration()
            if config != self.displayed_config():
                raise DomainError("Enregistrer les paramètres affichés avant de préparer l’envoi.")
            if not config.enabled:
                raise DomainError("Activer et configurer l’assistance avant l’envoi.")
            self.expected = self.current()
            self.request = AssistanceRequest(
                self.expected.part_id,
                self.expected.revision,
                self.context.toPlainText(),
                self.expected.values if self.include_values.isChecked() else (),
            )
            self.payload.setText(
                f"Destination : {config.destination}\nModèle : "
                f"{config.model}\n\nDonnées utilisateur exactes :\n{self.request.payload}\n\n"
                "Instruction fixe : proposer uniquement constructeur, MPN, catégorie et notes "
                "en JSON. Aucune exécution ni navigation."
            )
        except DomainError as error:
            self.message.show_message(str(error), "warning")

    def send(self) -> None:
        if self.worker or self.request is None or not self.consent.isChecked():
            return
        try:
            if self.current() != self.expected:
                raise DomainError("Identification modifiée ; préparer à nouveau le contexte.")
            config = self.service.configuration()
            if config != self.displayed_config():
                raise DomainError("Configuration modifiée ; préparer à nouveau l’envoi.")
            worker = AssistanceWorker(self.service, self.request, config, self)
            self.worker = worker
            worker.completed.connect(self.completed)
            worker.failed.connect(lambda message: self.message.show_message(message, "error"))
            worker.finished.connect(self.finished)
            self.set_busy(True)
            self.message.show_message("Analyse en cours… aucune donnée locale modifiée.")
            worker.start()
        except DomainError as error:
            self.message.show_message(str(error), "warning")

    def completed(self, proposal: MetadataProposal) -> None:
        try:
            if self.current() != self.expected:
                raise DomainError("Identification modifiée pendant l’analyse ; suggestion écartée.")
            self.review(proposal)
            self.message.show_message(
                "Suggestions à comparer ; aucun changement accepté automatiquement."
            )
        except DomainError as error:
            self.message.show_message(str(error), "warning")

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.config_widget,
            self.config_toggle,
            self.context,
            self.include_values,
            self.preview_button,
            self.consent,
        ):
            widget.setEnabled(not busy)
        self.send_button.setEnabled(
            not busy and self.consent.isChecked() and self.request is not None
        )
        self.busy_changed.emit(busy)

    def finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker:
            worker.deleteLater()
        self.request, self.expected = None, None
        self.consent.setChecked(False)
        self.set_busy(False)
