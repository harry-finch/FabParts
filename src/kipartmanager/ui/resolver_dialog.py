"""Explicit candidate comparison and choice; mechanical roles target a shared package."""

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QWidget,
)

from kipartmanager.application.previews import Previews
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.application.third_party_assets import ThirdPartyResolver
from kipartmanager.domain.documentation import Identification, MetadataField
from kipartmanager.domain.entities import Asset, AssetType, DomainError, Package, Part
from kipartmanager.domain.resolution import Candidate, ResourceChoice, allowed_roles
from kipartmanager.ui.components import (
    DetailText,
    Disclosure,
    MessageBanner,
    PageHeader,
    PageLayout,
    label,
    origin_label,
    primary,
)
from kipartmanager.ui.preview_dialog import PreviewDialog
from kipartmanager.ui.third_party_panel import ThirdPartyPanel


class ResolverDialog(QDialog):
    def __init__(
        self,
        resolver: LocalResolver,
        owner: Part | Package,
        parent: QWidget | None = None,
        *,
        remote_open: Callable[[AssetType, str], None] | None = None,
        third_party: ThirdPartyResolver | None = None,
        identification: Identification | None = None,
        previews: Previews | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapmagic: ThirdPartyPanel | None = None
        self.previews = previews
        self.remote_open = remote_open
        self.resolver, self.owner_entity = resolver, owner
        self.target_owner: Part | Package = owner
        self.expected: ResourceChoice | None = None
        self.candidates: tuple[Candidate, ...] = ()
        self.setWindowTitle(f"Résoudre les ressources — {owner.name}")
        self.resize(820, 760)
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                "Résoudre les ressources" if third_party else "Ressources locales",
                "Comparer les sources et choisir explicitement une ressource.",
            )
        )
        self.role = QComboBox()
        roles = list(allowed_roles(owner))
        if isinstance(owner, Part) and owner.package_id is not None:
            roles.extend((AssetType.FOOTPRINT, AssetType.MODEL_3D))
        for role in roles:
            self.role.addItem(role.value, role.value)
        layout.addWidget(self.role)
        outer_layout = layout
        self.provider_tabs = QTabWidget()
        self.provider_tabs.setDocumentMode(True)
        local = QWidget()
        self.provider_tabs.addTab(local, "Sources locales et officielles")
        if third_party is not None:
            outer_layout.addWidget(self.provider_tabs, 1)
            layout = PageLayout(local)
            layout.setContentsMargins(0, 0, 0, 0)
        self.query = QLineEdit(owner.name)
        layout.addWidget(self.query)
        self.search_button = QPushButton("Rechercher les candidats locaux")
        self.search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.role.currentIndexChanged.connect(lambda: self.search())
        layout.addWidget(self.search_button)
        self.current = QLabel()
        self.current.setWordWrap(True)
        layout.addWidget(self.current)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        self.candidate_details = DetailText(
            "Sélectionnez un candidat pour consulter son identité et son hash."
        )
        self.candidate_details.setMaximumHeight(120)
        self.candidate_summary = label("Sélectionnez une ressource à examiner.", "body")
        layout.addWidget(self.candidate_summary)
        details = Disclosure("Provenance et identité du candidat")
        details.body.addWidget(self.candidate_details)
        layout.addWidget(details)
        self.preview_button = QPushButton("Inspecter le candidat…")
        self.preview_button.setVisible(previews is not None)
        self.preview_button.clicked.connect(self.inspect_candidate)
        layout.addWidget(self.preview_button)
        self.items.currentRowChanged.connect(self.show_candidate)
        self.confirm_replace = QCheckBox("Je confirme le remplacement du choix actuel")
        layout.addWidget(self.confirm_replace)
        self.select_button = QPushButton("Choisir le candidat sélectionné")
        self.select_button.clicked.connect(self.select)
        layout.addWidget(primary(self.select_button))
        self.message = MessageBanner()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.notices = QListWidget()
        self.notices.setMaximumHeight(80)
        self.notices.hide()
        layout.addWidget(self.notices)
        self.remote_button = QPushButton("Compléter avec la recherche officielle distante…")
        self.remote_button.setVisible(remote_open is not None)
        self.remote_button.clicked.connect(self.open_remote)
        layout.addWidget(self.remote_button)
        if third_party is not None:
            self.snapmagic = ThirdPartyPanel(
                third_party,
                self.search,
                mpn=identification.value(MetadataField.MPN) if identification else "",
                manufacturer=identification.value(MetadataField.MANUFACTURER)
                if identification
                else "",
            )
            self.provider_tabs.addTab(self.snapmagic, "SnapMagic · optionnel")
            self.snapmagic.imported.connect(self.search)
            self.snapmagic.busy_changed.connect(lambda busy: self.role.setEnabled(not busy))
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        outer_layout.addWidget(close)
        self.search()
        self.show_candidate()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.has_pending_previews():
            event.ignore()
            return
        if self.snapmagic is not None and self.snapmagic.worker is not None:
            self.snapmagic.message.show_message("Attendre la fin de la requête avant de fermer.")
            event.ignore()
        else:
            super().closeEvent(event)

    def accept(self) -> None:
        if self.has_pending_previews():
            return
        if self.snapmagic is not None and self.snapmagic.worker is not None:
            self.snapmagic.message.show_message("Attendre la fin de la requête avant de fermer.")
            return
        super().accept()

    def reject(self) -> None:
        if self.has_pending_previews():
            return
        if self.snapmagic is not None and self.snapmagic.worker is not None:
            self.snapmagic.message.show_message("Attendre la fin de la requête avant de fermer.")
            return
        super().reject()

    def has_pending_previews(self) -> bool:
        for preview in self.findChildren(PreviewDialog):
            if preview.worker is not None:
                preview.message.show_message(
                    "Attendre la fin de la préparation 3D avant de fermer."
                )
                preview.raise_()
                return True
        return False

    def open_remote(self) -> None:
        role = AssetType(self.role.currentData())
        if self.remote_open is not None and role is not AssetType.DATASHEET:
            self.search()  # Always consider existing local resources first.
            self.accept()
            self.remote_open(role, self.query.text())

    def inspect_candidate(self) -> None:
        index = self.items.currentRow()
        if self.previews is not None and 0 <= index < len(self.candidates):
            PreviewDialog(self.previews, self.candidates[index].choice, self).show()

    def show_candidate(self) -> None:
        index = self.items.currentRow()
        self.preview_button.setEnabled(
            0 <= index < len(self.candidates) and not self.candidates[index].unavailable
        )
        self.preview_button.setToolTip(
            "Inspection indépendante du choix. STEP : FreeCAD local requis."
        )
        self.select_button.setEnabled(
            0 <= index < len(self.candidates) and not self.candidates[index].unavailable
        )
        if 0 <= index < len(self.candidates):
            candidate = self.candidates[index]
            self.candidate_summary.setText(
                candidate.name
                + " · "
                + origin_label(candidate.origin)
                + "\n"
                + (candidate.unavailable or "Choix explicite requis · validation à effectuer")
            )
            self.candidate_details.setText(
                f"{candidate.name} — {candidate.origin}\n{candidate.choice.key}\n"
                f"SHA-256 : {candidate.sha256 or 'absent'}\n{candidate.unavailable or 'UNCHECKED'}"
                + (f"\nSource : {candidate.asset.source}" if candidate.asset else "")
                + (
                    f"\n{candidate.asset.provenance.summary}"
                    if candidate.asset and candidate.asset.provenance
                    else ""
                )
            )
        else:
            self.candidate_summary.setText("Sélectionnez une ressource à examiner.")
            self.candidate_details.setText(
                "Sélectionnez un candidat pour consulter ses informations."
            )

    def target(self) -> Part | Package:
        owner = self.resolver.owner(type(self.owner_entity), self.owner_entity.id)
        if self.role.currentData() in (AssetType.FOOTPRINT.value, AssetType.MODEL_3D.value):
            if isinstance(owner, Part):
                if owner.package_id is None:
                    raise DomainError(
                        "Associer un package au composant pour ses ressources mécaniques."
                    )
                return self.resolver.owner(Package, owner.package_id)
        return owner

    def search(self) -> None:
        if self.snapmagic is not None:
            self.snapmagic.set_kind(AssetType(self.role.currentData()))
        self.remote_button.setEnabled(self.role.currentData() != AssetType.DATASHEET.value)
        self.items.clear()
        self.candidates = ()
        self.expected = None
        self.confirm_replace.setChecked(False)
        self.notices.clear()
        self.notices.hide()
        try:
            self.target_owner = self.target()
            role = AssetType(self.role.currentData())
            self.expected = next(
                (c for c in self.resolver.choices(self.target_owner) if c.asset_type is role), None
            )
            context = f"Ressources de {self.target_owner.name}"
            if isinstance(self.target_owner, Package):
                context += " · package partagé"
            current_name = "aucun"
            if self.expected and self.expected.reference:
                current_name = self.expected.reference.identifier
            elif self.expected and self.expected.asset_id:
                current_name = self.resolver.catalogue.require(Asset, self.expected.asset_id).name
            context += "\nChoix actuel : " + current_name
            self.current.setText(context)
            result = self.resolver.search(self.target_owner, role, self.query.text())
            self.candidates = result.candidates
            for candidate in self.candidates:
                state = candidate.unavailable or (
                    "Référence indexée — fichier vérifié au choix ; UNCHECKED"
                    if candidate.choice.reference
                    else "Fichier géré vérifié — UNCHECKED"
                )
                self.items.addItem(f"{candidate.name} — {candidate.origin}\n{state}")
            self.notices.setVisible(bool(result.notices))
            for notice in result.notices:
                self.notices.addItem(notice)
            self.message.setText(
                f"{len(self.candidates)} candidats ; aucun choix automatique."
                if self.candidates
                else "Aucun candidat local trouvé ; choix actuel conservé."
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def select(self) -> None:
        index = self.items.currentRow()
        if index < 0:
            self.message.setText("Sélectionner un candidat dans la liste.")
            return
        try:
            if self.target().id != self.target_owner.id:
                raise DomainError("Le package du composant a changé ; relancer la recherche.")
            self.resolver.select(
                self.target_owner,
                self.candidates[index],
                expected=self.expected,
                replace_existing=self.confirm_replace.isChecked(),
            )
            self.search()
            self.message.setText("Choix enregistré ; associations et fichiers existants conservés.")
        except DomainError as error:
            self.message.show_message(str(error), "error")
