"""SnapMagic candidate inspection inside the existing resource resolution workflow."""

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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

from kipartmanager.application.third_party_assets import ThirdPartyResolver
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.third_party_assets import (
    AssetQuery,
    ProviderState,
    ThirdPartyCandidate,
    ThirdPartyConfiguration,
    ThirdPartyDownload,
    ThirdPartySearch,
)
from kipartmanager.ui.components import (
    DetailText,
    EmptyState,
    MessageBanner,
    PageLayout,
    SectionCard,
    label,
    primary,
)


class ThirdPartyWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: ThirdPartyResolver,
        query: AssetQuery,
        parent: QWidget,
        candidate: ThirdPartyCandidate | None = None,
    ) -> None:
        super().__init__(parent)
        self.service, self.query, self.candidate = service, query, candidate

    def run(self) -> None:
        try:
            result = (
                self.service.download(self.candidate)
                if self.candidate
                else self.service.search(self.query)
            )
            self.completed.emit(result)
        except DomainError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Fournisseur indisponible ; résolution locale conservée.")


class ThirdPartyPanel(QWidget):
    imported = Signal()
    busy_changed = Signal(bool)

    def __init__(
        self,
        service: ThirdPartyResolver,
        before_search: Callable[[], None],
        *,
        mpn: str = "",
        manufacturer: str = "",
    ) -> None:
        super().__init__()
        self.service, self.before_search = service, before_search
        self.kind = AssetType.SYMBOL
        self.worker: ThirdPartyWorker | None = None
        self.candidates: tuple[ThirdPartyCandidate, ...] = ()
        layout = PageLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            label(
                "Source tierce après les ressources utilisateur, gérées et officielles. "
                "Recherche explicite par MPN exact ; aucun choix automatique."
            )
        )
        config = QHBoxLayout()
        self.enabled = QCheckBox("Activer SnapMagic")
        self.save_button = QPushButton("Enregistrer")
        self.save_button.clicked.connect(self.configure)
        config.addWidget(self.enabled, 1)
        config.addWidget(self.save_button)
        layout.addLayout(config)
        self.state_label = label("")
        layout.addWidget(self.state_label)
        form = QFormLayout()
        self.mpn = QLineEdit(mpn)
        self.mpn.setMaxLength(256)
        self.mpn.setPlaceholderText("Référence constructeur exacte")
        self.manufacturer = QLineEdit(manufacturer)
        self.manufacturer.setMaxLength(256)
        self.manufacturer.setPlaceholderText("Facultatif ; identité exacte si renseignée")
        form.addRow("MPN *", self.mpn)
        form.addRow("Constructeur", self.manufacturer)
        layout.addLayout(form)
        self.search_button = primary(QPushButton("Rechercher sur SnapMagic"))
        self.search_button.clicked.connect(self.search)
        self.mpn.returnPressed.connect(self.search)
        layout.addWidget(self.search_button)
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self.show_candidate)
        self.results = QStackedWidget()
        self.results.addWidget(self.items)
        self.empty = EmptyState(
            "Aucune recherche lancée", "Saisir un MPN et activer le fournisseur."
        )
        self.results.addWidget(self.empty)
        self.results.setCurrentIndex(1)
        card = SectionCard("Candidat tiers · non sélectionné")
        self.details = DetailText("La recherche n’importe aucun fichier.")
        card.body.addWidget(self.details, 1)
        self.import_button = QPushButton("Importer le candidat inspecté")
        self.import_button.clicked.connect(self.download)
        card.body.addWidget(primary(self.import_button))
        split = QSplitter()
        split.addWidget(self.results)
        split.addWidget(card)
        split.setSizes([340, 440])
        layout.addWidget(split, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        for field in (self.mpn, self.manufacturer):
            field.textChanged.connect(self.clear_results)
        self.enabled.toggled.connect(self.clear_results)
        try:
            self.enabled.setChecked(service.configuration().enabled)
            self.refresh_state()
        except DomainError as error:
            self.state_label.setText(str(error))
        self.show_candidate()

    def refresh_state(self) -> None:
        descriptions = {
            ProviderState.DISABLED: "Désactivé · les recherches locales restent disponibles.",
            ProviderState.NOT_CONFIGURED: "Non configuré · accès API partenaire ou secret absent.",
            ProviderState.CONTRACT_REQUIRED: (
                "Secret présent · contrat API partenaire non installé."
            ),
            ProviderState.READY: "Accès partenaire configuré · requêtes explicites uniquement.",
        }
        self.state_label.setText(descriptions[self.service.state()])

    def configure(self) -> None:
        try:
            self.service.configure(ThirdPartyConfiguration(self.enabled.isChecked()))
            self.clear_results()
            self.refresh_state()
            self.message.show_message("Activation enregistrée ; aucune requête lancée.", "success")
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def set_kind(self, kind: AssetType) -> None:
        if kind != self.kind:
            self.kind = kind
            self.clear_results()
        self.search_button.setEnabled(kind is not AssetType.DATASHEET and self.worker is None)

    def clear_results(self) -> None:
        self.candidates = ()
        self.items.clear()
        self.results.setCurrentIndex(1)
        self.empty.title.setText("Aucune recherche lancée")
        self.empty.description.setText("Relire le MPN, puis lancer une recherche explicite.")
        self.message.clear()
        self.show_candidate()

    def show_candidate(self) -> None:
        row = self.items.currentRow()
        candidate = self.candidates[row] if 0 <= row < len(self.candidates) else None
        self.import_button.setEnabled(candidate is not None and self.worker is None)
        self.details.setText(
            f"{candidate.name}\nSnapMagic / SnapEDA · DISTANT · TRUSTED_THIRD_PARTY\n\n"
            f"MPN : {candidate.mpn}\nConstructeur : {candidate.manufacturer or '—'}\n"
            f"Package : {candidate.package or '—'}\nFormat : {candidate.extension}\n"
            f"Source : {candidate.source_url}\nRésolution : {candidate.resolved_at}\n\n"
            f"Licence : {candidate.license_name or 'non communiquée'}\n{candidate.license_url}\n"
            f"Attribution : {candidate.attribution or 'non communiquée'}\n"
            f"Redistribution : {candidate.redistribution.value}\n"
            f"Droits : {candidate.rights_reference or 'non établis'}\n\n"
            "Import local seulement ; choisir et qualifier ensuite par le workflow habituel."
            if candidate
            else "Inspecter un candidat pour lire sa provenance et ses droits."
        )

    def search(self) -> None:
        self.before_search()  # Consider all existing local tiers first, without online calls.
        self.start(None)

    def download(self) -> None:
        row = self.items.currentRow()
        if 0 <= row < len(self.candidates):
            self.start(self.candidates[row])

    def start(self, candidate: ThirdPartyCandidate | None) -> None:
        if self.worker is not None:
            return
        try:
            if self.service.configuration() != ThirdPartyConfiguration(self.enabled.isChecked()):
                raise DomainError("Enregistrer l’activation affichée avant de rechercher.")
            self.service.require_ready()
            query = AssetQuery(self.mpn.text().strip(), self.manufacturer.text().strip(), self.kind)
        except DomainError as error:
            self.message.show_message(str(error), "warning")
            return
        if candidate is None:
            self.clear_results()
        self.message.show_message(
            "Téléchargement en cours…" if candidate else "Recherche en cours…"
        )
        worker = ThirdPartyWorker(self.service, query, self, candidate)
        self.worker = worker
        worker.completed.connect(self.completed)
        worker.failed.connect(lambda message: self.message.show_message(message, "error"))
        worker.finished.connect(self.finished)
        self.busy(True)
        worker.start()

    def completed(self, result: ThirdPartySearch | ThirdPartyDownload) -> None:
        if isinstance(result, ThirdPartySearch):
            self.candidates = result.candidates
            self.items.clear()
            for candidate in self.candidates:
                self.items.addItem(
                    f"{candidate.name}\n{candidate.mpn} · {candidate.extension} · Tiers"
                )
            self.results.setCurrentIndex(0 if self.candidates else 1)
            self.empty.title.setText("Aucune correspondance exacte")
            self.empty.description.setText("Les ressources actuelles sont conservées.")
            self.message.show_message(
                f"{len(self.candidates)} candidat(s) ; aucun import ni choix automatique. "
                + " ".join(result.notices)
            )
        else:
            try:
                asset = self.service.import_download(result)
                self.message.show_message(
                    f"{asset.name} importé · UNCHECKED. Choisir et qualifier explicitement ; "
                    "vérifier les droits avant redistribution.",
                    "success",
                )
                self.imported.emit()
            except DomainError as error:
                self.message.show_message(str(error), "error")

    def busy(self, value: bool) -> None:
        self.progress.setVisible(value)
        for widget in (
            self.enabled,
            self.save_button,
            self.mpn,
            self.manufacturer,
            self.search_button,
            self.items,
        ):
            widget.setEnabled(not value)
        self.show_candidate()
        self.busy_changed.emit(value)

    def finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.busy(False)
        self.set_kind(self.kind)
