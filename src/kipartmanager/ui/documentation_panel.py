"""Per-component identification review and additive datasheet management."""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from kipartmanager.application.assistance import Assistance
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.previews import Previews
from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.documentation import (
    FIELD_LABELS,
    DocumentDetails,
    DocumentKind,
    FieldValue,
    Identification,
    MetadataField,
    MetadataProposal,
    MetadataSource,
    PartDocument,
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, DomainError, Part
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ui.assistance_panel import AssistancePanel
from kipartmanager.ui.components import (
    DetailText,
    Disclosure,
    MessageBanner,
    PageHeader,
    PageLayout,
    ScrollPanel,
    SectionCard,
    label,
    origin_label,
    primary,
)
from kipartmanager.ui.preview_dialog import PreviewDialog
from kipartmanager.ui.theme import M, S


class PDFWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: Documentation, url: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.service, self.url = service, url

    def run(self) -> None:
        try:
            self.completed.emit(self.service.download(self.url))
        except DomainError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Erreur de l’adaptateur constructeur ; documents locaux conservés.")


class DocumentationPanel(QWidget):
    changed = Signal()

    def __init__(
        self,
        service: Documentation,
        assistance: Assistance | None = None,
        *,
        previews: Previews | None = None,
    ) -> None:
        super().__init__()
        self.assistance_panel: AssistancePanel | None = None
        self.service = service
        self.previews = previews
        self.proposal: MetadataProposal | None = None
        self.expected: Identification | None = None
        self.records: tuple[PartDocument, ...] = ()
        self.worker: PDFWorker | None = None
        self.pending: tuple[UUID, DocumentDetails] | None = None
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                "Documentation du composant",
                "Identification traçable, enrichissements relus et PDF conservés localement.",
            )
        )
        self.parts = QComboBox()
        self.parts.setAccessibleName("Composant à documenter")
        self.parts.currentIndexChanged.connect(self.load_part)
        layout.addWidget(self.parts)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.identification_page = QWidget()
        self.documents_page = QWidget()
        self.tabs.addTab(self.identification_page, "Identification")
        self.tabs.addTab(self.documents_page, "Datasheets && documents")
        layout.addWidget(self.tabs, 1)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        self.build_identification()
        self.build_documents()
        if assistance is not None:
            self.assistance_panel = AssistancePanel(
                assistance, lambda: self.service.identification(self.part_id()), self.review_ai
            )
            self.assistance_panel.busy_changed.connect(self.ai_busy)
            self.assistance_panel.context.textChanged.connect(self.message.clear)
            self.assistance_panel.preview_button.clicked.connect(self.message.clear)
            self.tabs.addTab(self.assistance_panel, "Assistance IA · optionnelle")
        self.refresh()

    def has_active_worker(self) -> bool:
        return self.worker is not None or (
            self.assistance_panel is not None and self.assistance_panel.worker is not None
        )

    def ai_busy(self, busy: bool) -> None:
        self.parts.setEnabled(not busy)
        self.identification_page.setEnabled(not busy)
        self.documents_page.setEnabled(not busy)

    def review_ai(self, proposal: MetadataProposal) -> None:
        self.preview(proposal)
        # AI changes start unchecked, including previously empty fields.
        for row in range(self.comparison.rowCount()):
            item = self.comparison.item(row, 0)
            assert item is not None
            item.setCheckState(Qt.CheckState.Unchecked)
        self.tabs.setCurrentIndex(0)

    def build_identification(self) -> None:
        layout = PageLayout(self.identification_page)
        layout.setContentsMargins(S, M, S, S)
        self.identification_stack = QStackedWidget()
        layout.addWidget(self.identification_stack, 1)
        edit_page = QWidget()
        edit_layout = PageLayout(edit_page)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.identification_stack.addWidget(edit_page)
        review_page = QWidget()
        review_layout = PageLayout(review_page)
        review_layout.setContentsMargins(0, 0, 0, 0)
        self.identification_stack.addWidget(review_page)
        review_body = QWidget()
        review_body_layout = PageLayout(review_body)
        review_body_layout.setContentsMargins(0, 0, S, 0)
        review_layout.addWidget(ScrollPanel(review_body), 1)
        fields = QWidget()
        form = QFormLayout(fields)
        form.setVerticalSpacing(M)
        self.fields: dict[MetadataField, QLineEdit] = {}
        for field, title in FIELD_LABELS.items():
            editor = QLineEdit()
            editor.setMaxLength(4096)
            form.addRow(title, editor)
            self.fields[field] = editor
        self.source_label = QLineEdit("Saisie locale")
        self.source_reference = QLineEdit("user:local")
        self.source_origin = self.origins()
        form.addRow("Nom de source *", self.source_label)
        form.addRow("Référence / URL de source *", self.source_reference)
        form.addRow("Origine déclarée", self.source_origin)
        edit_layout.addWidget(ScrollPanel(fields), 1)
        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Comparer la saisie")
        self.preview_button.clicked.connect(self.preview_manual)
        self.json_button = QPushButton("Lire une proposition JSON…")
        self.json_button.clicked.connect(self.read_json)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.json_button)
        edit_layout.addLayout(buttons)
        self.proposal_source = label(
            "Aucune proposition : les valeurs enregistrées sont conservées."
        )
        review_body_layout.addWidget(self.proposal_source)
        reference_details = Disclosure("Source et référence technique de la proposition")
        self.proposal_reference = DetailText()
        self.proposal_reference.setMinimumHeight(90)
        reference_details.body.addWidget(self.proposal_reference)
        review_body_layout.addWidget(reference_details)
        self.comparison = QTableWidget(0, 3)
        self.comparison.setHorizontalHeaderLabels(
            ["Champ à accepter", "Valeur actuelle", "Proposition"]
        )
        self.comparison.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison.horizontalHeader().setStretchLastSection(True)
        self.comparison.setMinimumHeight(180)
        review_body_layout.addWidget(self.comparison, 1)
        self.replace_values = QCheckBox(
            "Je confirme le remplacement des valeurs existantes cochées"
        )
        review_body_layout.addWidget(self.replace_values)
        actions = QHBoxLayout()
        self.accept_button = primary(QPushButton("Accepter les champs cochés"))
        self.accept_button.clicked.connect(self.accept_proposal)
        ignore = QPushButton("Ignorer la proposition")
        ignore.clicked.connect(self.load_part)
        actions.addWidget(ignore)
        actions.addWidget(self.accept_button)
        review_layout.addLayout(actions)
        self.history = DetailText()
        self.history.setMaximumHeight(140)
        self.history.hide()
        history_button = QPushButton("Historique et provenance des champs")
        history_button.setCheckable(True)
        history_button.toggled.connect(self.history.setVisible)
        edit_layout.addWidget(history_button)
        edit_layout.addWidget(self.history)

    @staticmethod
    def origins() -> QComboBox:
        combo = QComboBox()
        for origin, title in (
            (AssetOrigin.USER_PROVIDED, "Saisie / fichier utilisateur"),
            (AssetOrigin.MANUFACTURER, "Constructeur"),
            (AssetOrigin.TRUSTED_THIRD_PARTY, "Source tierce acceptée explicitement"),
        ):
            combo.addItem(title, origin.value)
        return combo

    def part_id(self) -> UUID:
        identity = self.parts.currentData()
        if identity is None:
            raise DomainError("Créer ou choisir un composant à documenter.")
        return UUID(identity)

    def refresh(self) -> None:
        selected = self.parts.currentData()
        self.parts.blockSignals(True)
        self.parts.clear()
        for part in self.service.catalogue.list_entities(Part):
            self.parts.addItem(part.name, str(part.id))
        index = self.parts.findData(selected)
        if index >= 0:
            self.parts.setCurrentIndex(index)
        self.parts.blockSignals(False)
        self.load_part()

    def open_part(self, part: Part) -> None:
        self.refresh()
        self.parts.setCurrentIndex(self.parts.findData(str(part.id)))
        self.load_part()

    def load_part(self) -> None:
        if self.has_active_worker():
            return
        if self.assistance_panel is not None:
            self.assistance_panel.context.clear()
            self.assistance_panel.invalidate()
        self.message.clear()
        self.identification_stack.setCurrentIndex(0)
        self.document_form_toggle.setChecked(False)
        self.doc_title.clear()
        self.doc_revision.clear()
        self.doc_date.clear()
        self.doc_language.clear()
        self.doc_kind.setCurrentIndex(0)
        self.doc_source.setText("Fichier utilisateur")
        self.doc_reference.clear()
        self.doc_origin.setCurrentIndex(0)
        self.url.clear()
        self.proposal = None
        self.expected = None
        self.comparison.setRowCount(0)
        self.proposal_reference.clear()
        self.replace_values.setChecked(False)
        self.accept_button.setEnabled(False)
        self.proposal_source.setText(
            "Aucune proposition : les valeurs enregistrées sont conservées."
        )
        available = self.parts.currentData() is not None
        self.tabs.setEnabled(available)
        if not available:
            self.message.show_message(
                "Aucun composant à documenter. Ajoutez une référence au catalogue."
            )
            return
        try:
            self.expected = self.service.identification(self.part_id())
            for field, editor in self.fields.items():
                editor.setText(self.expected.value(field))
            self.source_label.setText("Saisie locale")
            self.source_reference.setText("user:local")
            self.source_origin.setCurrentIndex(0)
            self.history.setText(
                "\n\n".join(
                    f"{event.recorded_at} · {event.source.label} · {event.source.origin.value}\n"
                    f"Source : {event.source.reference}\n"
                    + "\n".join(
                        f"{FIELD_LABELS[value.field]} : {old.value or '—'} → {value.value or '—'}"
                        for old, value in zip(event.before, event.after, strict=True)
                    )
                    for event in reversed(self.expected.history)
                )
                or "Aucun enrichissement accepté."
            )
            self.refresh_documents()
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def preview_manual(self) -> None:
        try:
            proposal = MetadataProposal(
                MetadataSource(
                    self.source_label.text(),
                    self.source_reference.text(),
                    AssetOrigin(self.source_origin.currentData()),
                ),
                tuple(FieldValue(field, editor.text()) for field, editor in self.fields.items()),
            )
            self.preview(proposal)
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def read_json(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Lire une proposition sans modifier le catalogue", "", "JSON (*.json)"
        )
        if source:
            try:
                self.preview(self.service.read_proposal(source))
            except DomainError as error:
                self.message.show_message(str(error), "error")

    def preview(self, proposal: MetadataProposal) -> None:
        self.expected = self.service.identification(self.part_id())
        self.proposal = proposal
        self.replace_values.setChecked(False)
        self.comparison.setRowCount(len(proposal.values))
        conflicts = self.expected.conflicts(proposal)
        for row, value in enumerate(proposal.values):
            item = QTableWidgetItem(
                FIELD_LABELS[value.field] + (" · conflit" if value.field in conflicts else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, value.field.value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked if value.field in conflicts else Qt.CheckState.Checked
            )
            self.comparison.setItem(row, 0, item)
            self.comparison.setItem(
                row, 1, QTableWidgetItem(self.expected.value(value.field) or "—")
            )
            self.comparison.setItem(row, 2, QTableWidgetItem(value.value or "(vider)"))
        self.comparison.resizeColumnsToContents()
        self.proposal_source.setText(
            f"Source proposée : {proposal.source.label} · "
            f"{origin_label(proposal.source.origin.value)}"
        )
        self.proposal_reference.setText(proposal.source.reference)
        self.accept_button.setEnabled(True)
        self.identification_stack.setCurrentIndex(1)
        self.message.show_message(
            f"{len(conflicts)} conflit(s). Relisez la source et cochez les champs à accepter.",
            "warning" if conflicts else "info",
        )

    def accept_proposal(self) -> None:
        if self.proposal is None or self.expected is None:
            return
        try:
            selected: list[MetadataField] = []
            for row in range(self.comparison.rowCount()):
                item = self.comparison.item(row, 0)
                if item is not None and item.checkState() == Qt.CheckState.Checked:
                    selected.append(MetadataField(item.data(Qt.ItemDataRole.UserRole)))
            fields = tuple(selected)
            self.service.accept(
                self.expected,
                self.proposal,
                fields,
                replace_existing=self.replace_values.isChecked(),
            )
            self.load_part()
            self.changed.emit()
            self.message.show_message(
                "Champs acceptés et provenance enregistrée ; fiche et ressources conservées.",
                "success",
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def build_documents(self) -> None:
        layout = PageLayout(self.documents_page)
        layout.setContentsMargins(S, M, S, S)
        self.document_form_toggle = QPushButton("Ajouter ou décrire un PDF…")
        self.document_form_toggle.setCheckable(True)
        layout.addWidget(self.document_form_toggle)
        self.document_stack = QStackedWidget()
        layout.addWidget(self.document_stack, 1)
        browse_page = QWidget()
        browse_layout = PageLayout(browse_page)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        self.document_stack.addWidget(browse_page)
        add_page = QWidget()
        add_layout = PageLayout(add_page)
        add_layout.setContentsMargins(0, 0, 0, 0)
        self.document_stack.addWidget(add_page)
        add_body = QWidget()
        add_body_layout = PageLayout(add_body)
        add_body_layout.setContentsMargins(0, 0, S, 0)
        add_layout.addWidget(ScrollPanel(add_body), 1)
        self.document_form_toggle.toggled.connect(self.toggle_document_form)
        self.config_toggle = QPushButton("Téléchargement constructeur · désactivé — configurer")
        self.config_toggle.setCheckable(True)
        add_body_layout.addWidget(self.config_toggle)
        config = SectionCard("Domaines constructeurs autorisés")
        self.enabled = QCheckBox("Autoriser les téléchargements PDF explicites")
        self.domains = QLineEdit()
        self.domains.setPlaceholderText(
            "Domaines exacts séparés par une virgule ; aucun domaine préautorisé"
        )
        config.body.addWidget(self.enabled)
        config.body.addWidget(self.domains)
        save = QPushButton("Enregistrer l’autorisation")
        save.clicked.connect(self.configure)
        config.body.addWidget(save)
        add_body_layout.addWidget(config)
        config.hide()
        self.config_toggle.toggled.connect(config.setVisible)
        try:
            value = self.service.configuration()
            self.enabled.setChecked(value.enabled)
            self.domains.setText(", ".join(value.domains))
            self.config_label(value)
        except DomainError as error:
            self.message.show_message(str(error), "error")
        split = QSplitter()
        self.document_list = QListWidget()
        self.document_list.currentRowChanged.connect(self.show_document)
        split.addWidget(self.document_list)
        card = SectionCard("Document conservé")
        self.document_text = DetailText(
            "Aucun document décrit. Importez un PDF ou documentez un PDF déjà géré."
        )
        card.body.addWidget(self.document_text, 1)
        self.document_preview_button = QPushButton("Lire le PDF…")
        self.document_preview_button.setVisible(self.previews is not None)
        self.document_preview_button.clicked.connect(self.inspect_document)
        card.body.addWidget(self.document_preview_button)
        self.retrieve_button = QPushButton("Restituer une copie du PDF…")
        self.retrieve_button.clicked.connect(self.retrieve)
        card.body.addWidget(self.retrieve_button)
        split.addWidget(card)
        split.setSizes([450, 350])
        browse_layout.addWidget(split, 1)
        fields = QWidget()
        form = QFormLayout(fields)
        form.setVerticalSpacing(M)
        self.pdfs = QComboBox()
        self.pdfs.currentIndexChanged.connect(self.use_pdf)
        form.addRow("PDF géré existant", self.pdfs)
        self.doc_title = QLineEdit()
        self.doc_revision = QLineEdit()
        self.doc_date = QLineEdit()
        self.doc_date.setPlaceholderText("AAAA-MM-JJ, facultatif")
        self.doc_language = QLineEdit()
        self.doc_kind = QComboBox()
        for kind, title in (
            (DocumentKind.DATASHEET, "Datasheet"),
            (DocumentKind.APPLICATION_NOTE, "Note d’application"),
            (DocumentKind.ERRATA, "Errata"),
        ):
            self.doc_kind.addItem(title, kind.value)
        self.doc_source = QLineEdit("Fichier utilisateur")
        self.doc_reference = QLineEdit()
        self.doc_origin = self.origins()
        self.url = QLineEdit()
        self.url.setPlaceholderText(
            "URL HTTPS finale du PDF, sur un domaine explicitement autorisé"
        )
        for title, field in (
            ("Titre *", self.doc_title),
            ("Révision", self.doc_revision),
            ("Date", self.doc_date),
            ("Langue", self.doc_language),
            ("Type de document", self.doc_kind),
            ("Nom de source *", self.doc_source),
            ("Référence de source *", self.doc_reference),
            ("Origine déclarée", self.doc_origin),
            ("URL de téléchargement", self.url),
        ):
            form.addRow(title, field)
        add_body_layout.addWidget(fields)
        self.download_button_hint = label(
            "Téléchargement : l’URL devient la source constructeur. "
            "La datasheet choisie reste inchangée."
        )
        add_body_layout.addWidget(self.download_button_hint)
        actions = QHBoxLayout()
        self.existing_button = QPushButton("Décrire le PDF géré")
        self.existing_button.clicked.connect(self.add_existing)
        self.local_button = QPushButton("Importer un nouveau PDF…")
        self.local_button.clicked.connect(self.import_local)
        self.download_button = QPushButton("Télécharger un nouveau PDF")
        self.download_button.clicked.connect(self.download)
        for button in (self.existing_button, self.local_button, self.download_button):
            actions.addWidget(button)
        add_layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

    def toggle_document_form(self, checked: bool) -> None:
        self.document_stack.setCurrentIndex(1 if checked else 0)
        self.document_form_toggle.setText(
            "Revenir aux documents conservés" if checked else "Ajouter ou décrire un PDF…"
        )

    def use_pdf(self) -> None:
        identity = self.pdfs.currentData()
        if identity is not None:
            asset = self.service.catalogue.require(Asset, UUID(identity))
            if not self.doc_title.text().strip():
                self.doc_title.setText(asset.name)
            if not self.doc_reference.text().strip():
                self.doc_reference.setText(asset.source or f"asset:{asset.id}")
            index = self.doc_origin.findData(asset.origin.value)
            if index >= 0:
                self.doc_origin.setCurrentIndex(index)

    def details(self, *, remote: bool = False) -> DocumentDetails:
        source = MetadataSource(
            self.doc_source.text(),
            self.url.text().strip() if remote else self.doc_reference.text(),
            AssetOrigin.MANUFACTURER if remote else AssetOrigin(self.doc_origin.currentData()),
        )
        return DocumentDetails(
            self.doc_title.text(),
            source,
            self.doc_revision.text(),
            self.doc_date.text().strip(),
            self.doc_language.text(),
            DocumentKind(self.doc_kind.currentData()),
        )

    def refresh_documents(self) -> None:
        self.records = self.service.documents(self.part_id())
        selected = self.document_list.currentRow()
        self.document_list.clear()
        for record in self.records:
            self.document_list.addItem(
                f"{record.title}\n{record.kind.value} · "
                f"Rév. {record.revision or '—'} · {record.language or '—'}"
            )
        if self.records:
            self.document_list.setCurrentRow(min(max(selected, 0), len(self.records) - 1))
        self.pdfs.clear()
        self.pdfs.addItem("Choisir un PDF du catalogue", None)
        for asset in self.service.catalogue.list_entities(Asset):
            if asset.asset_type is AssetType.DATASHEET and asset.file:
                self.pdfs.addItem(asset.name, str(asset.id))
        self.show_document()

    def inspect_document(self) -> None:
        row = self.document_list.currentRow()
        if self.previews is not None and 0 <= row < len(self.records):
            record = self.records[row]
            PreviewDialog(
                self.previews, ResourceChoice(AssetType.DATASHEET, asset_id=record.asset_id), self
            ).show()

    def show_document(self) -> None:
        row = self.document_list.currentRow()
        self.document_preview_button.setEnabled(0 <= row < len(self.records))
        self.retrieve_button.setEnabled(0 <= row < len(self.records))
        if 0 <= row < len(self.records):
            record = self.records[row]
            asset = self.service.catalogue.require(Asset, record.asset_id)
            self.document_text.setText(
                f"{record.title}\n{record.kind.value} · Révision : {record.revision or '—'}\n"
                f"Date : {record.document_date or '—'} · Langue : {record.language or '—'}\n\n"
                f"Source : {record.source.label}\n{record.source.reference}\n"
                f"Origine : {record.source.origin.value}\nAjout : {record.recorded_at}\n\n"
                f"SHA-256 : {asset.file.sha256 if asset.file else 'absent'}\n\n"
                "Associé au composant ; choix et qualification restent explicites "
                "dans les ressources locales."
            )
        else:
            self.document_text.setText(
                "Aucun document décrit. Les PDF existants restent disponibles "
                "dans le sélecteur et les ressources locales."
            )

    def add_existing(self) -> None:
        try:
            identity = self.pdfs.currentData()
            if identity is None:
                raise DomainError("Choisir un PDF géré à documenter.")
            self.service.add_existing(self.part_id(), UUID(identity), self.details())
            self.document_added()
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def import_local(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Ajouter un PDF sans remplacer les documents existants", "", "PDF (*.pdf)"
        )
        if not source:
            return
        if not self.doc_title.text().strip():
            self.doc_title.setText(Path(source).name)
        if not self.doc_reference.text().strip():
            self.doc_reference.setText(source)
        try:
            self.service.import_local(self.part_id(), source, self.details())
            self.document_added()
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def document_added(self) -> None:
        self.document_form_toggle.setChecked(False)
        self.refresh_documents()
        self.changed.emit()
        self.message.show_message(
            "Document ajouté ; PDF précédents et choix actuel conservés. "
            "Choisir et valider dans les ressources locales.",
            "success",
        )

    def retrieve(self) -> None:
        row = self.document_list.currentRow()
        if not 0 <= row < len(self.records):
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Restituer sans écraser un fichier existant", "", "PDF (*.pdf)"
        )
        if destination:
            try:
                self.service.retrieve(self.part_id(), self.records[row].id, destination)
                self.message.show_message("Copie du PDF restituée et vérifiée.", "success")
            except DomainError as error:
                self.message.show_message(str(error), "error")

    def config_label(self, config: DatasheetConfiguration) -> None:
        self.config_toggle.setText(
            f"Téléchargement constructeur : {'activé' if config.enabled else 'désactivé'} "
            f"· {len(config.domains)} domaine(s) — configurer"
        )

    def configure(self) -> None:
        try:
            config = DatasheetConfiguration(
                self.enabled.isChecked(),
                tuple(v.strip() for v in self.domains.text().split(",") if v.strip()),
            )
            self.service.configure(config)
            self.config_label(config)
            self.config_toggle.setChecked(False)
            self.message.show_message(
                "Autorisation enregistrée localement ; aucun téléchargement lancé.", "success"
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def download(self) -> None:
        if self.has_active_worker():
            return
        try:
            shown = DatasheetConfiguration(
                self.enabled.isChecked(),
                tuple(v.strip() for v in self.domains.text().split(",") if v.strip()),
            )
            if shown != self.service.configuration():
                raise DomainError("Enregistrer l’autorisation affichée avant téléchargement.")
            shown.authorize(self.url.text().strip())
            details = self.details(remote=True)
            identity = self.part_id()
            self.pending = (identity, details)
            worker = PDFWorker(self.service, self.url.text().strip(), self)
            self.worker = worker
            worker.completed.connect(self.downloaded)
            worker.failed.connect(lambda text: self.message.show_message(text, "error"))
            worker.finished.connect(self.finished)
            self.parts.setEnabled(False)
            self.tabs.setEnabled(False)
            self.progress.show()
            self.message.show_message("Téléchargement PDF constructeur en cours…")
            worker.start()
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def downloaded(self, result: DatasheetDownload) -> None:
        if self.pending is None:
            return
        try:
            self.service.import_download(self.pending[0], result, self.pending[1])
            self.document_added()
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def finished(self) -> None:
        worker, self.worker = self.worker, None
        self.pending = None
        if worker is not None:
            worker.deleteLater()
        self.parts.setEnabled(True)
        self.tabs.setEnabled(True)
        self.progress.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.has_active_worker():
            event.ignore()
        else:
            super().closeEvent(event)
