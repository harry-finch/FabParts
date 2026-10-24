"""Catalogue, managed files and optional local KiCad index UI."""

from typing import cast
from uuid import UUID

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kipartmanager import __version__
from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.assistance import Assistance
from kipartmanager.application.bundles import Bundles
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.documentation import Documentation
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.previews import Previews
from kipartmanager.application.publications import Publications
from kipartmanager.application.publisher import LocalPublisher
from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.application.third_party_assets import ThirdPartyResolver
from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.entities import (
    Asset,
    AssetType,
    Collection,
    DomainError,
    Entity,
    Inventory,
    Location,
    Package,
    Part,
    StockItem,
)
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ui.asset_actions import FILTER, ImportDialog
from kipartmanager.ui.branding import PRODUCT_NAME, PRODUCT_SUBTITLE, application_icon
from kipartmanager.ui.component_panel import ComponentPanel
from kipartmanager.ui.components import (
    DetailText,
    Disclosure,
    EmptyState,
    MessageBanner,
    PageHeader,
    PageLayout,
    ScrollPanel,
    SearchBar,
    SectionCard,
    StatusBadge,
    label,
    origin_label,
    quiet,
)
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.documentation_panel import DocumentationPanel
from kipartmanager.ui.entity_dialog import EntityDialog
from kipartmanager.ui.icons import icon
from kipartmanager.ui.kicad_panel import KiCadPanel
from kipartmanager.ui.preview_dialog import PreviewDialog
from kipartmanager.ui.publications_panel import PublicationsPanel
from kipartmanager.ui.publisher_dialog import PublisherDialog
from kipartmanager.ui.remote_kicad_panel import RemoteKiCadPanel
from kipartmanager.ui.resolver_dialog import ResolverDialog
from kipartmanager.ui.theme import SIDEBAR_WIDTH, L, M, apply_theme
from kipartmanager.ui.validation_dialog import ValidationDialog


class EntityPanel(QWidget):
    def __init__(self, catalogue: Catalogue, kind: type[Entity], window: "MainWindow") -> None:
        super().__init__(window)
        self.catalogue, self.kind, self.host_window = catalogue, kind, window
        self.entities: list[Entity] = []
        layout = PageLayout(self)
        titles = {
            Part: "Composants",
            Package: "Packages partagés",
            Asset: "Fichiers & ressources",
            Inventory: "Inventaires",
            StockItem: "Inventaire",
            Location: "Emplacements",
            Collection: "Bibliothèques",
        }
        descriptions = {
            Part: "Vos références de composants et leurs ressources KiCad.",
            Package: HELP["package"],
            Asset: HELP["asset"],
            Inventory: HELP["inventory"],
            StockItem: "Quantités possédées par composant, inventaire et emplacement.",
            Location: "Les emplacements physiques de vos composants.",
            Collection: HELP["library"],
        }
        create = QPushButton("Ajouter un composant" if kind is Part else "Ajouter")
        create.clicked.connect(lambda: self.edit(False))
        layout.addWidget(PageHeader(titles[kind], descriptions[kind], create))
        self.search = SearchBar()
        self.inventory_id: UUID | None = None
        self.part_id: UUID | None = None
        self.search.textChanged.connect(self.filter_rows)
        layout.addWidget(self.search)
        splitter = QSplitter()
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self.show_details)
        self.items.itemDoubleClicked.connect(lambda: self.edit(True))
        self.empty = EmptyState(
            "Aucun élément pour le moment", descriptions[kind] + " Utilisez Ajouter pour commencer."
        )
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.items)
        self.list_stack.addWidget(self.empty)
        splitter.addWidget(self.list_stack)
        self.details_card = SectionCard("Détails de la sélection")
        self.badge = StatusBadge()
        self.details_card.body.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = DetailText("Sélectionnez une ligne pour consulter ses informations.")
        self.summary = label("Sélectionnez une ligne pour consulter ses informations.", "body")
        self.details_card.body.addWidget(self.summary)
        self.technical_details = Disclosure("Provenance et détails")
        self.technical_details.body.addWidget(self.details)
        self.details.setMinimumHeight(130)
        self.details_card.body.addWidget(self.technical_details)
        edit = quiet(QPushButton("Modifier"))
        edit.setIcon(icon("pencil"))
        edit.clicked.connect(lambda: self.edit(True))
        self.selection_actions: list[QPushButton] = [edit]
        self.details_card.body.addWidget(edit)
        self.actions_layout = self.details_card.body
        scroll = ScrollPanel(self.details_card)
        scroll.setMinimumWidth(245)
        splitter.addWidget(scroll)
        splitter.setSizes([650, 320])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        if kind is Asset and window.imports is not None:
            for action_title, action in (
                ("Importer un fichier", "import"),
                ("Associer un fichier", "attach"),
                ("Vérifier l'intégrité", "verify"),
                ("Restituer une copie", "retrieve"),
            ):
                button = QPushButton(action_title)
                button.clicked.connect(lambda checked=False, value=action: self.file_action(value))
                self.actions_layout.addWidget(button)
                if action != "import":
                    self.selection_actions.append(button)
        if kind in (Part, Package) and window.resolver is not None:
            button = QPushButton("Résoudre les ressources")
            button.clicked.connect(self.resolve)
            self.actions_layout.addWidget(button)
            self.selection_actions.append(button)
        if kind in (Part, Collection) and window.validation is not None:
            button = QPushButton("Valider localement")
            button.clicked.connect(self.validate_local)
            self.actions_layout.addWidget(button)
            self.selection_actions.append(button)
        if kind is Collection and window.publisher is not None:
            button = QPushButton("Exporter pour KiCad")
            button.clicked.connect(self.publish)
            self.actions_layout.addWidget(button)
            self.selection_actions.append(button)
        if kind is Collection and window.publications is not None:
            button = QPushButton("Versions / historique")
            button.clicked.connect(self.open_publications)
            self.actions_layout.addWidget(button)
            self.selection_actions.append(button)
        self.preview_button = QPushButton("Inspecter le fichier…")
        self.preview_button.setVisible(kind is Asset and window.previews is not None)
        self.preview_button.clicked.connect(self.inspect_file)
        self.actions_layout.insertWidget(1, self.preview_button)
        self.selection_actions.append(self.preview_button)
        self.refresh()

    def inspect_file(self) -> None:
        index = self.items.currentRow()
        if 0 <= index < len(self.entities):
            asset = self.entities[index]
            if isinstance(asset, Asset):
                self.host_window.inspect_resource(
                    ResourceChoice(asset.asset_type, asset_id=asset.id)
                )

    def open_publications(self) -> None:
        index = self.items.currentRow()
        if 0 <= index < len(self.entities):
            collection = self.entities[index]
            if isinstance(collection, Collection):
                self.host_window.open_publications(collection)

    def publish(self) -> None:
        index = self.items.currentRow()
        publisher = self.host_window.publisher
        if index < 0 or publisher is None:
            self.message.setText("Sélectionner une collection.")
            return
        collection = self.entities[index]
        if isinstance(collection, Collection):
            PublisherDialog(publisher, collection, self).exec()

    def validate_local(self) -> None:
        index = self.items.currentRow()
        service = self.host_window.validation
        if index < 0 or service is None:
            self.message.setText("Sélectionner un composant ou une collection.")
            return
        subject = self.entities[index]
        if isinstance(subject, (Part, Collection)):
            ValidationDialog(service, subject, self).exec()
            self.show_details()

    def resolve(self) -> None:
        index = self.items.currentRow()
        resolver = self.host_window.resolver
        if index < 0 or resolver is None:
            self.message.setText("Sélectionner un composant ou package.")
            return
        owner = self.entities[index]
        if isinstance(owner, (Part, Package)):
            self.host_window.resource_dialog(owner, self).exec()
            self.host_window.refresh()

    def filter_rows(self) -> None:
        query = self.search.text().casefold()
        visible = 0
        for index in range(self.items.count()):
            item = self.items.item(index)
            assert item is not None
            entity = self.entities[index]
            hidden = query not in item.text().casefold()
            if isinstance(entity, StockItem):
                hidden |= self.inventory_id is not None and entity.inventory_id != self.inventory_id
                hidden |= self.part_id is not None and entity.part_id != self.part_id
            item.setHidden(hidden)
            visible += not hidden
        self.list_stack.setCurrentIndex(0 if visible else 1)
        if self.entities:
            self.empty.title.setText("Aucun résultat")
            self.empty.description.setText("Essayez un autre nom ou effacez la recherche.")
        if self.items.currentRow() >= 0 and self.items.item(self.items.currentRow()).isHidden():
            self.items.setCurrentRow(-1)

    def show_details(self) -> None:
        index = self.items.currentRow()
        selected = 0 <= index < len(self.entities)
        for button in self.selection_actions:
            button.setEnabled(selected)
        if not selected:
            self.summary.setText("Sélectionnez une ligne pour consulter ses informations.")
            self.badge.set_status("")
            self.details.setText("Sélectionnez une ligne pour consulter ses informations.")
            return
        entity = self.entities[index]
        text = getattr(entity, "name", "Stock")
        state = ""
        if isinstance(entity, Part):
            state = entity.state.value
            package = (
                self.catalogue.require(Package, entity.package_id).name
                if entity.package_id
                else "Non associé"
            )
            text += (
                f"\n\nDescription\n{entity.description or '—'}\n\nPackage\n{package}"
                f"\n\nAssets associés : {len(entity.asset_ids)}"
            )
        elif isinstance(entity, Package):
            text += (
                f"\n\n{entity.description or 'Sans description'}"
                f"\nAssets associés : {len(entity.asset_ids)}"
            )
        elif isinstance(entity, Asset):
            state = origin_label(entity.origin.value)
            text += (
                f"\n\nType : {entity.asset_type.value}\nValidation : {entity.validation_state}"
                f"\nSource : {entity.source or '—'}"
            )
            if entity.file:
                text += (
                    f"\n\nFichier\n{entity.file.original_name}\n{entity.file.size_bytes} octets"
                    f"\n\nSHA-256\n{entity.file.sha256}"
                )
            else:
                text += "\n\nAucun fichier associé"
            if entity.provenance:
                text += "\n\nProvenance et droits\n" + entity.provenance.summary
        elif isinstance(entity, Collection):
            text += (
                f"\n\n{len(entity.part_ids)} composants exposés à KiCad"
                "\nLe stock n'influence pas cette sélection."
                "\n\nValidez la collection avant de construire ses bibliothèques."
            )
            text += "\n\nComposants\n" + (
                "\n".join(
                    self.catalogue.require(Part, identity).name for identity in entity.part_ids
                )
                or "Aucun composant. Ajoutez-en depuis une fiche ou Modifier."
            )
            if self.host_window.validation:
                try:
                    qualification = self.host_window.validation.qualification(entity)
                    state = qualification.state
                    text += "\n\nQualification actuelle : " + state
                except DomainError as error:
                    text += "\n\n" + str(error)
        elif isinstance(entity, Inventory):
            text += (
                "\n\nInventaire physique\nConsultez Quantités "
                "dans cet espace pour les stocks possédés."
            )
        elif isinstance(entity, StockItem):
            text = self.catalogue.require(Part, entity.part_id).name
            inventory = self.catalogue.require(Inventory, entity.inventory_id).name
            location = (
                self.catalogue.require(Location, entity.location_id).name
                if entity.location_id
                else "Non renseignée"
            )
            text += (
                f"\n\nQuantité : {entity.quantity}\nInventaire : {inventory}"
                f"\nLocalisation : {location}"
            )
        self.preview_button.setEnabled(isinstance(entity, Asset) and entity.file is not None)
        self.preview_button.setToolTip(
            "Inspection sans modifier le fichier ni sa validation. STEP : FreeCAD local requis."
        )
        summary = getattr(entity, "name", "")
        if isinstance(entity, Asset):
            summary += f"\n{entity.asset_type.value} · {entity.validation_state}"
            summary += "\n" + (
                entity.file.original_name if entity.file else "Aucun fichier associé"
            )
        elif isinstance(entity, Package):
            summary += f"\n{entity.description or 'Package partagé'}"
            summary += f"\n{len(entity.asset_ids)} fichiers associés"
        elif isinstance(entity, Collection):
            summary += f"\n{len(entity.part_ids)} composants exposés à KiCad"
        elif isinstance(entity, StockItem):
            summary = (
                f"{self.catalogue.require(Part, entity.part_id).name}\nQuantité : {entity.quantity}"
            )
            summary += (
                "\nInventaire : " + self.catalogue.require(Inventory, entity.inventory_id).name
            )
            summary += "\nEmplacement : " + (
                self.catalogue.require(Location, entity.location_id).name
                if entity.location_id
                else "Non renseigné"
            )
        self.summary.setText(summary)
        self.badge.set_status(state)
        self.details.setText(text)

    def refresh(self) -> None:
        index = self.items.currentRow()
        identity = self.entities[index].id if 0 <= index < len(self.entities) else None
        self.entities = list(self.catalogue.list_entities(self.kind))
        self.items.clear()
        for entity in self.entities:
            if isinstance(entity, StockItem):
                part = self.catalogue.require(Part, entity.part_id)
                inventory = self.catalogue.require(Inventory, entity.inventory_id)
                location = (
                    self.catalogue.require(Location, entity.location_id).name
                    if entity.location_id
                    else "Sans emplacement"
                )
                text = f"{part.name} — {entity.quantity}\n{inventory.name} · {location}"
            else:
                text = entity.name
                if isinstance(entity, Part):
                    text += f"\n{entity.state.value} · {entity.description or 'Sans description'}"
                elif isinstance(entity, Asset):
                    text += f"\n{entity.asset_type.value} · {entity.origin.value}"
                elif isinstance(entity, Collection):
                    text += f"\n{len(entity.part_ids)} composants · Bibliothèque KiCad"
                elif isinstance(entity, Inventory):
                    text += "\nStock physique"
            self.items.addItem(text)
        if identity:
            self.items.setCurrentRow(
                next((i for i, e in enumerate(self.entities) if e.id == identity), -1)
            )
        self.filter_rows()
        self.show_details()

    def edit(self, existing: bool) -> None:
        index = self.items.currentRow()
        if existing and index < 0:
            return
        dialog = EntityDialog(
            self.catalogue, self.kind, self.entities[index] if existing else None, self
        )
        if self.kind is StockItem and not existing:
            for key, identity in (("inventory", self.inventory_id), ("part", self.part_id)):
                if identity:
                    dialog.combos[key].setCurrentIndex(dialog.combos[key].findData(str(identity)))
        self.host_window.show_editor(dialog)

    def file_action(self, action: str) -> None:
        imports = self.host_window.imports
        if imports is None:
            return
        self.message.clear()
        try:
            if action == "import":
                source, _ = QFileDialog.getOpenFileName(self, "Importer un fichier", "", FILTER)
                if source:
                    dialog = ImportDialog(imports, source)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        self.host_window.refresh()
                return
            index = self.items.currentRow()
            if index < 0:
                self.message.setText("Sélectionner un asset.")
                return
            entity = self.entities[index]
            if not isinstance(entity, Asset):
                return
            if action == "attach":
                source, _ = QFileDialog.getOpenFileName(self, "Associer un fichier", "", FILTER)
                if source:
                    imports.attach_file(entity.id, source)
                    self.host_window.refresh()
            elif action == "verify":
                imports.verify(entity.id)
                self.message.setText("Intégrité SHA-256 vérifiée. Validation sémantique inchangée.")
            elif action == "retrieve":
                suggested = entity.file.original_name if entity.file else ""
                destination, _ = QFileDialog.getSaveFileName(
                    self,
                    "Restituer une copie",
                    suggested,
                    options=QFileDialog.Option.DontConfirmOverwrite,
                )
                if destination:
                    imports.retrieve(entity.id, destination)
                    self.message.setText("Copie restituée ; fichier canonique préservé.")
        except DomainError as error:
            self.message.show_message(str(error), "error")


class MainWindow(QMainWindow):
    def __init__(
        self,
        catalogue: Catalogue,
        imports: AssetImports | None = None,
        libraries: KiCadLibraries | None = None,
        resolver: LocalResolver | None = None,
        validation: LocalValidation | None = None,
        publisher: LocalPublisher | None = None,
        publications: Publications | None = None,
        bundles: Bundles | None = None,
        remote_libraries: RemoteLibraries | None = None,
        documentation: Documentation | None = None,
        third_party: ThirdPartyResolver | None = None,
        assistance: Assistance | None = None,
        previews: Previews | None = None,
    ) -> None:
        super().__init__()
        self.editor: EntityDialog | None = None
        self.previews = previews
        self.third_party = third_party
        self.documentation = documentation
        self.assistance = assistance
        self.remote_libraries = remote_libraries
        self.imports = imports
        self.resolver = resolver
        self.validation = validation
        self.publisher = publisher
        self.publications = publications
        self.catalogue = catalogue
        self.setWindowTitle(PRODUCT_NAME)
        self.setWindowIcon(application_icon())
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app)
        self.resize(1200, 800)
        self.setMinimumSize(820, 600)
        content = QWidget()
        shell = QVBoxLayout(content)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        topbar = QWidget()
        topbar.setObjectName("topbar")
        identity = QHBoxLayout(topbar)
        identity.setContentsMargins(M, 6, L, 6)
        identity.setSpacing(M)
        logo = QLabel()
        logo.setObjectName("applicationLogo")
        logo.setAccessibleName(f"Logo {PRODUCT_NAME}")
        logo.setPixmap(self.windowIcon().pixmap(QSize(32, 32)))
        logo.setFixedSize(32, 32)
        identity.addWidget(logo)
        brand = QLabel(PRODUCT_NAME)
        brand.setProperty("role", "brand")
        identity.addWidget(brand)
        subtitle = QLabel(PRODUCT_SUBTITLE)
        subtitle.setProperty("role", "muted")
        identity.addWidget(subtitle)
        identity.addStretch()
        settings_button = quiet(QPushButton("Paramètres"))
        settings_button.setIcon(icon("settings"))
        settings_button.clicked.connect(self.open_settings)
        identity.addWidget(settings_button)
        shell.addWidget(topbar)
        workspace = QWidget()
        layout = QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(M, L, M, M)
        side.addWidget(label("ESPACE DE TRAVAIL", "section"))
        side.addSpacing(M)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setIconSize(QSize(16, 16))
        self.navigation.setAccessibleName("Navigation principale")
        side.addWidget(self.navigation, 1)
        layout.addWidget(sidebar)
        self.tabs = QStackedWidget()
        layout.addWidget(self.tabs, 1)
        self.components_panel = ComponentPanel(catalogue, self)
        self.entity_panels = {
            kind: EntityPanel(catalogue, kind, self)
            for kind in (Package, Asset, Inventory, StockItem, Location, Collection)
        }
        self.panels: list[ComponentPanel | EntityPanel] = [
            self.components_panel,
            *self.entity_panels.values(),
        ]
        self.component_workspace = WorkspaceTabs()
        self.component_workspace.addTab(self.components_panel, "Catalogue")
        for kind, title in ((Package, "Packages partagés"), (Asset, "Fichiers && ressources")):
            self.component_workspace.addTab(self.entity_panels[kind], title)
        self.documentation_panel = (
            DocumentationPanel(documentation, assistance, previews=previews)
            if documentation
            else None
        )
        if self.documentation_panel:
            self.documentation_panel.changed.connect(self.refresh)
            self.component_workspace.addTab(self.documentation_panel, "Documentation")
        self.add_page("Composants", self.component_workspace)
        self.inventory_workspace = WorkspaceTabs()
        stock_panel = self.entity_panels[StockItem]
        controls = QHBoxLayout()
        self.inventory_filter = QComboBox()
        self.inventory_filter.setAccessibleName("Inventaire physique à consulter")
        self.inventory_filter.setToolTip("Filtrer les quantités par inventaire physique.")
        self.inventory_filter.currentIndexChanged.connect(self.filter_inventory)
        controls.addWidget(self.inventory_filter, 1)
        clear_part = QPushButton("Tous les composants")
        clear_part.clicked.connect(self.clear_stock_part)
        controls.addWidget(clear_part)
        self.stock_context = label("")
        controls.addWidget(self.stock_context, 1)
        cast(QVBoxLayout, stock_panel.layout()).insertLayout(1, controls)
        self.inventory_workspace.addTab(stock_panel, "Quantités")
        self.inventory_workspace.addTab(self.entity_panels[Inventory], "Inventaires")
        self.inventory_workspace.addTab(self.entity_panels[Location], "Emplacements")
        self.add_page("Inventaire", self.inventory_workspace)
        self.add_page("Bibliothèques", self.entity_panels[Collection])
        self.kicad_panel = (
            KiCadPanel(libraries, previews=previews) if libraries is not None else None
        )
        self.remote_panel = RemoteKiCadPanel(remote_libraries) if remote_libraries else None
        self.kicad_workspace = WorkspaceTabs()
        if self.kicad_panel is not None and self.remote_panel is not None:
            self.kicad_workspace.addTab(self.kicad_panel, "Installation locale")
        if self.remote_panel is not None:
            self.remote_panel.imported.connect(self.refresh)
            self.kicad_workspace.addTab(self.remote_panel, "Officiel distant · optionnel")
        if self.remote_panel is None and self.kicad_panel is not None:
            self.add_page("KiCad local", self.kicad_panel)
        elif self.kicad_workspace.count():
            self.add_page("KiCad local", self.kicad_workspace)
        self.publications_panel = (
            PublicationsPanel(catalogue, publications, bundles) if publications else None
        )
        if self.publications_panel is not None:
            self.publications_panel.imported.connect(self.refresh)
            self.add_page("Publications", self.publications_panel)
        self.settings = QWidget()
        settings_layout = QVBoxLayout(self.settings)
        settings_layout.setContentsMargins(L, L, L, L)
        settings_layout.addWidget(
            PageHeader(
                "Paramètres",
                "Configuration des ressources locales et fonctionnement de l'application.",
            )
        )
        settings_card = SectionCard("Application locale")
        settings_card.body.addWidget(label(PRODUCT_NAME, "heading"))
        settings_card.body.addWidget(label(PRODUCT_SUBTITLE))
        settings_card.body.addWidget(
            label(
                "Le catalogue et les fichiers gérés restent sur ce poste. "
                "Aucun serveur ni fournisseur IA n'est requis."
            )
        )
        if self.kicad_panel:
            settings_card.body.addWidget(
                label(
                    "Dossiers KiCad : configurez les sources puis réindexez. "
                    "Les bibliothèques sources restent en lecture seule."
                )
            )
            configure = QPushButton("Configurer les dossiers KiCad")
            configure.clicked.connect(self.open_kicad_configuration)
            settings_card.body.addWidget(configure)
        if self.remote_panel is not None:
            settings_card.body.addWidget(
                label(
                    "Recherche officielle distante : désactivée par défaut. "
                    "Aucun accès réseau au démarrage."
                )
            )
            remote_button = QPushButton("Configurer la recherche officielle distante")
            remote_button.clicked.connect(lambda: self.open_remote())
            settings_card.body.addWidget(remote_button)
        settings_layout.addWidget(settings_card)
        settings_layout.addStretch()
        self.add_page("Paramètres", self.settings)
        self.navigation.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.navigation.setCurrentRow)
        self.navigation.setCurrentRow(0)
        shell.addWidget(workspace, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addWidget(QLabel("Local • Sans serveur"))
        self.statusBar().addPermanentWidget(QLabel(f"{PRODUCT_NAME} · {__version__}"))
        self.setCentralWidget(content)
        self.refresh_inventory_filter()

    def open_settings(self) -> None:
        self.show_page(self.settings)

    def add_page(self, title: str, page: QWidget) -> None:
        self.tabs.addWidget(page)
        item = QListWidgetItem(
            icon(
                {
                    "Composants": "cpu",
                    "Inventaire": "boxes",
                    "Bibliothèques": "library",
                    "KiCad local": "circuit-board",
                    "Publications": "package-check",
                    "Paramètres": "settings",
                }[title]
            ),
            title,
        )
        self.navigation.addItem(item)

    def show_editor(self, dialog: EntityDialog) -> None:
        if self.editor is not None and self.editor.isVisible():
            self.editor.error.show_message(
                "Enregistrez ou annulez la fiche ouverte pour continuer."
            )
            self.editor.raise_()
            self.editor.activateWindow()
            dialog.deleteLater()
            return
        self.editor = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(self.refresh)
        dialog.finished.connect(lambda result: setattr(self, "editor", None))
        dialog.show()

    def show_page(self, page: QWidget) -> None:
        if self.remote_panel is not None and (
            page is self.kicad_panel or page is self.remote_panel
        ):
            self.kicad_workspace.setCurrentWidget(page)
            page = self.kicad_workspace
        self.tabs.setCurrentWidget(page)

    def open_remote(self, role: AssetType | None = None, query: str = "") -> None:
        if self.remote_panel is not None:
            if role is not None and self.remote_panel.worker is None:
                self.remote_panel.kind.setCurrentIndex(self.remote_panel.kind.findData(role.value))
                self.remote_panel.query.setText(query)
            self.show_page(self.remote_panel)

    def open_libraries(self) -> None:
        self.show_page(self.entity_panels[Collection])

    def open_publications(self, collection: Collection) -> None:
        if self.publications_panel:
            self.publications_panel.collections.setCurrentIndex(
                self.publications_panel.collections.findData(str(collection.id))
            )
            self.show_page(self.publications_panel)

    def open_packages(self) -> None:
        self.component_workspace.setCurrentIndex(1)
        self.show_page(self.component_workspace)

    def open_assets(self) -> None:
        self.component_workspace.setCurrentIndex(2)
        self.show_page(self.component_workspace)

    def resource_dialog(self, owner: Part | Package, parent: QWidget) -> ResolverDialog:
        if self.resolver is None:
            raise DomainError("Resolver local indisponible.")
        identification = None
        if self.documentation is not None and isinstance(owner, Part):
            try:
                identification = self.documentation.identification(owner.id)
            except DomainError:
                pass
        return ResolverDialog(
            self.resolver,
            owner,
            parent,
            remote_open=self.open_remote if self.remote_panel else None,
            third_party=self.third_party,
            identification=identification,
            previews=self.previews,
        )

    def inspect_resource(self, choice: ResourceChoice) -> None:
        if self.previews is not None:
            PreviewDialog(self.previews, choice, self).show()

    def open_assistance(self, part: Part) -> None:
        panel = self.documentation_panel
        if (
            panel is not None
            and panel.assistance_panel is not None
            and not panel.has_active_worker()
        ):
            self.open_documentation(part)
            panel.tabs.setCurrentWidget(panel.assistance_panel)

    def open_documentation(self, part: Part) -> None:
        if (
            self.documentation_panel is not None
            and not self.documentation_panel.has_active_worker()
        ):
            self.documentation_panel.open_part(part)
            self.component_workspace.setCurrentWidget(self.documentation_panel)
            self.show_page(self.component_workspace)

    def open_stock(self, part: Part) -> None:
        panel = self.entity_panels[StockItem]
        panel.part_id = part.id
        self.stock_context.setText("Composant : " + part.name)
        self.inventory_workspace.setCurrentIndex(0)
        self.show_page(self.inventory_workspace)
        panel.filter_rows()

    def clear_stock_part(self) -> None:
        self.entity_panels[StockItem].part_id = None
        self.stock_context.clear()
        self.entity_panels[StockItem].filter_rows()

    def refresh_inventory_filter(self) -> None:
        current = self.inventory_filter.currentData()
        self.inventory_filter.blockSignals(True)
        self.inventory_filter.clear()
        self.inventory_filter.addItem("Tous les inventaires", None)
        for inventory in self.catalogue.list_entities(Inventory):
            self.inventory_filter.addItem(inventory.name, str(inventory.id))
        self.inventory_filter.setCurrentIndex(max(0, self.inventory_filter.findData(current)))
        self.inventory_filter.blockSignals(False)
        self.filter_inventory()

    def filter_inventory(self) -> None:
        panel = self.entity_panels[StockItem]
        identity = self.inventory_filter.currentData()
        panel.inventory_id = UUID(identity) if identity else None
        panel.filter_rows()

    def open_kicad_configuration(self) -> None:
        if self.kicad_panel:
            self.show_page(self.kicad_panel)
            self.kicad_panel.config_toggle.setChecked(True)

    def refresh(self) -> None:
        if (
            self.documentation_panel is not None
            and not self.documentation_panel.has_active_worker()
        ):
            self.documentation_panel.refresh()
        if self.publications_panel is not None:
            self.publications_panel.refresh()
        for panel in self.panels:
            panel.refresh()
        self.refresh_inventory_filter()

    def closeEvent(self, event: QCloseEvent) -> None:
        for preview in self.findChildren(PreviewDialog):
            if preview.worker is not None:
                preview.message.show_message(
                    "Attendre la fin de la préparation 3D avant de fermer."
                )
                preview.raise_()
                event.ignore()
                return
        if self.editor is not None and self.editor.isVisible():
            self.editor.error.show_message(
                "Enregistrez ou annulez la fiche ouverte pour continuer."
            )
            self.editor.raise_()
            self.editor.activateWindow()
            event.ignore()
            return
        if self.kicad_panel is not None and self.kicad_panel.worker is not None:
            self.kicad_panel.status.setText("Attendre la fin de la reconstruction avant de fermer.")
            event.ignore()
        elif self.documentation_panel is not None and self.documentation_panel.has_active_worker():
            self.documentation_panel.message.show_message(
                "Attendre la fin de l’opération de documentation avant de fermer."
            )
            event.ignore()
        elif self.remote_panel is not None and self.remote_panel.worker is not None:
            self.remote_panel.message.show_message(
                "Attendre la fin de l’opération distante avant de fermer."
            )
            event.ignore()
        else:
            super().closeEvent(event)


class WorkspaceTabs(QTabWidget):
    """Secondary tools stay in their task workspace instead of the sidebar."""

    def __init__(self) -> None:
        super().__init__()
        self.setDocumentMode(True)
        self.setContentsMargins(M, M, M, M)
