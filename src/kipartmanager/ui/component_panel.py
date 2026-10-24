"""Component workspace: useful catalogue columns and explicit local workflows."""

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.documentation import FIELD_LABELS, MetadataField
from kipartmanager.domain.entities import (
    Asset,
    AssetType,
    Collection,
    DomainError,
    Inventory,
    Location,
    Package,
    Part,
    PartState,
    StockItem,
)
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ui.asset_actions import FILTER, ImportDialog
from kipartmanager.ui.components import (
    Disclosure,
    EmptyState,
    MessageBanner,
    PageHeader,
    PageLayout,
    ResourceRow,
    ScrollPanel,
    SearchBar,
    SectionCard,
    StatusBadge,
    WorkflowStrip,
    label,
    origin_label,
    primary,
    quiet,
)
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.entity_dialog import EntityDialog
from kipartmanager.ui.icons import icon
from kipartmanager.ui.theme import COLORS, ROW_HEIGHT, M, S
from kipartmanager.ui.validation_dialog import ValidationDialog

if TYPE_CHECKING:
    from kipartmanager.ui.main_window import MainWindow


class ComponentPanel(QWidget):
    def __init__(self, catalogue: Catalogue, window: "MainWindow") -> None:
        super().__init__()
        self.catalogue, self.host_window = catalogue, window
        self.entities: list[Part] = []
        self._displayed_part_id: UUID | None = None
        self.choices: dict[AssetType, ResourceChoice] = {}
        self.next_action = "identify"
        layout = PageLayout(self)
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.AscendingOrder
        create = QPushButton("Ajouter un composant")
        create.setProperty("role", "secondary")
        create.setIcon(icon("plus"))
        create.clicked.connect(lambda: self.edit(False))
        layout.addWidget(
            PageHeader(
                "Composants", "Identifiez, préparez et exposez vos composants à KiCad.", create
            )
        )
        self.search = SearchBar("Rechercher un composant, un package ou un statut…")
        self.search.textChanged.connect(self.filter_rows)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        self.state_filter = QComboBox()
        self.state_filter.setAccessibleName("Filtrer les composants par état")
        self.state_filter.addItem("Tous les états", "")
        for state in PartState:
            self.state_filter.addItem(state.value, state.value)
        toolbar.addWidget(self.state_filter)
        layout.addLayout(toolbar)
        splitter = QSplitter()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Composant", "Package", "Ressources", "Statut", "Stock Lab"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 110), (2, 95), (3, 110), (4, 85)):
            self.table.setColumnWidth(column, width)
        self.table.setAccessibleName("Catalogue des composants")
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(self.sort_column, self.sort_order)
        header.sectionClicked.connect(self.sort_by_column)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.itemDoubleClicked.connect(lambda: self.edit(True))
        empty_add = primary(QPushButton("Ajouter un composant"))
        empty_add.setIcon(icon("plus", color=COLORS["PRIMARY_TEXT"]))
        empty_add.clicked.connect(lambda: self.edit(False))
        self.empty = EmptyState(
            "Aucun composant",
            "Ajoutez une référence, puis associez ses ressources et son stock.",
            empty_add,
        )
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.table)
        self.list_stack.addWidget(self.empty)
        splitter.addWidget(self.list_stack)
        self.detail_stack = QStackedWidget()
        self.detail_empty = EmptyState(
            "Votre fiche composant",
            "Sélectionnez une ligne pour voir le package, les ressources et les stocks.",
        )
        self.detail_stack.addWidget(self.detail_empty)
        body = QWidget()
        detail = QVBoxLayout(body)
        detail.setContentsMargins(S, 0, 0, 0)
        detail.setSpacing(M)
        identity = SectionCard("")
        self.name = label("", "heading")
        self.description = label("")
        self.badge = StatusBadge()
        name_row = QHBoxLayout()
        name_row.addWidget(self.name, 1)
        name_row.addWidget(self.badge)
        identity.body.addLayout(name_row)
        identity.body.addWidget(self.description)
        self.workflow = WorkflowStrip()
        identity.body.addWidget(self.workflow)
        self.context_button = primary(QPushButton())
        self.context_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.context_button.clicked.connect(self.advance)
        identity.body.addWidget(self.context_button)
        edit = quiet(QPushButton("Modifier"))
        edit.setToolTip("Modifier le composant sélectionné")
        edit.setIcon(icon("pencil"))
        edit.clicked.connect(lambda: self.edit(True))
        identity_tools = QHBoxLayout()
        identity_tools.setSpacing(4)
        identity_tools.addWidget(edit)
        detail.addWidget(identity)
        self.package_name = label("")
        self.package_name.setToolTip(HELP["package"])
        package_button = QPushButton("Package…")
        package_button.setToolTip(
            "Modifier le package partagé. Pour changer de package, modifiez le composant."
        )
        package_button.clicked.connect(self.edit_package)
        package_row = QHBoxLayout()
        package_row.addWidget(self.package_name, 1)
        package_row.addWidget(package_button)
        identity.body.insertLayout(2, package_row)
        self.stock_summary = label("")
        self.stock_summary.setParent(identity)
        self.stock_summary.hide()
        self.missing_summary = label("")
        self.missing_summary.setParent(identity)
        self.missing_summary.hide()
        resources = SectionCard("Ressources")
        self.resource_rows: dict[AssetType, ResourceRow] = {}
        for role, title in (
            (AssetType.SYMBOL, "Symbole"),
            (AssetType.FOOTPRINT, "Footprint"),
            (AssetType.MODEL_3D, "Modèle 3D · facultatif"),
            (AssetType.DATASHEET, "Datasheet · facultative"),
        ):
            row = ResourceRow(title)
            row.action.clicked.connect(
                lambda checked=False, value=role: self.resource_action(value)
            )
            row.inspect.setVisible(window.previews is not None)
            row.inspect.clicked.connect(
                lambda checked=False, value=role: self.inspect_resource(value)
            )
            self.resource_rows[role] = row
            resources.body.addWidget(row)
        detail.addWidget(resources)
        self.identification_text = label("")
        self.identification_text.setVisible(window.documentation is not None)
        self.identification_text.setParent(identity)
        self.identification_text.hide()
        self.identification_values: dict[MetadataField, QLabel] = {}
        profile_widget = QWidget()
        profile = QFormLayout(profile_widget)
        profile.setContentsMargins(0, 0, 0, 0)
        profile.setHorizontalSpacing(S)
        profile.setVerticalSpacing(4)
        for field in (MetadataField.MANUFACTURER, MetadataField.MPN, MetadataField.CATEGORY):
            value = label("—", "body")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            caption = QLabel(
                {
                    MetadataField.MANUFACTURER: "Fabricant",
                    MetadataField.MPN: "MPN",
                    MetadataField.CATEGORY: "Catégorie",
                }[field]
            )
            caption.setProperty("role", "muted")
            caption.setToolTip(FIELD_LABELS[field])
            profile.addRow(caption, value)
            self.identification_values[field] = value
        identity.body.insertWidget(2, profile_widget)
        profile_widget.setVisible(window.documentation is not None)
        documentation_button = quiet(QPushButton("Documents"))
        documentation_button.setToolTip("Identification et datasheets du composant")
        documentation_button.setVisible(window.documentation is not None)
        documentation_button.clicked.connect(self.open_documentation)
        identity_tools.addWidget(documentation_button)
        self.ai_button = quiet(QPushButton("Aide IA"))
        self.ai_button.setIcon(icon("sparkles"))
        self.ai_button.setToolTip(
            "Suggestions IA facultatives, à relire avant acceptation. Aucun envoi automatique."
        )
        self.ai_button.setVisible(
            window.documentation is not None and window.assistance is not None
        )
        self.ai_button.clicked.connect(self.open_assistance)
        identity_tools.addWidget(self.ai_button)
        for button in (edit, documentation_button, self.ai_button):
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        identity.body.addLayout(identity_tools)
        management = Disclosure(
            "Gérer les ressources", "Packages partagés et fichiers du catalogue"
        )
        tools = QHBoxLayout()
        packages_button = QPushButton("Packages partagés")
        packages_button.clicked.connect(window.open_packages)
        files_button = QPushButton("Gérer fichiers")
        files_button.clicked.connect(window.open_assets)
        tools.addWidget(packages_button)
        tools.addWidget(files_button)
        management.body.addLayout(tools)
        detail.addWidget(management)
        stock = SectionCard("Inventaire · quantités possédées")
        self.stock_text = label("")
        stock.body.addWidget(self.stock_text)
        stock_button = QPushButton("Gérer le stock de ce composant")
        stock_button.clicked.connect(self.open_stock)
        stock.body.addWidget(stock_button)
        detail.addWidget(stock)
        libraries = SectionCard("Bibliothèques · exposition à KiCad")
        self.memberships = label("")
        libraries.body.addWidget(self.memberships)
        self.collections = QComboBox()
        self.collections.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.collections.setMinimumContentsLength(12)
        self.collections.currentIndexChanged.connect(self.update_library_action)
        libraries.body.addWidget(self.collections)
        self.add_button = QPushButton("Ajouter à la bibliothèque")
        self.add_button.clicked.connect(self.add_to_library)
        libraries.body.addWidget(self.add_button)
        open_libraries = QPushButton("Valider / publier la bibliothèque")
        open_libraries.clicked.connect(window.open_libraries)
        libraries.body.addWidget(open_libraries)
        detail.addWidget(libraries)
        validation_card = SectionCard("Validation locale")
        self.qualification_badge = StatusBadge()
        validation_card.body.addWidget(self.qualification_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.validation_text = label("")
        validation_card.body.addWidget(self.validation_text)
        validate = QPushButton("Valider le composant")
        validate.clicked.connect(self.validate_local)
        validation_card.body.addWidget(validate)
        detail.insertWidget(2, validation_card)
        advanced = quiet(QPushButton("Informations techniques"))
        advanced.setCheckable(True)
        self.technical = label("")
        self.technical.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.technical.hide()
        advanced.toggled.connect(self.technical.setVisible)
        detail.addWidget(advanced)
        detail.addWidget(self.technical)
        detail.addStretch()
        scroll = ScrollPanel(body)
        scroll.setMinimumWidth(300)
        self.detail_stack.addWidget(scroll)
        splitter.addWidget(self.detail_stack)
        splitter.setSizes([620, 370])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.message = MessageBanner()
        layout.addWidget(self.message)
        self.selection_actions = [
            edit,
            package_button,
            stock_button,
            self.context_button,
            validate,
            self.add_button,
        ]
        self.state_filter.currentIndexChanged.connect(self.filter_rows)
        self.refresh()

    def sort_by_column(self, column: int) -> None:
        self.sort_order = (
            Qt.SortOrder.DescendingOrder
            if self.sort_column == column and self.sort_order == Qt.SortOrder.AscendingOrder
            else Qt.SortOrder.AscendingOrder
        )
        self.sort_column = column
        self.refresh()

    def selected(self) -> Part | None:
        row = self.table.currentRow()
        return (
            self.entities[row]
            if 0 <= row < len(self.entities) and not self.table.isRowHidden(row)
            else None
        )

    def resource_choices(self, part: Part) -> dict[AssetType, ResourceChoice]:
        resolver = self.host_window.resolver
        if resolver is None:
            return {}
        owners: list[Part | Package] = [part]
        if part.package_id:
            owners.append(self.catalogue.require(Package, part.package_id))
        return {choice.asset_type: choice for owner in owners for choice in resolver.choices(owner)}

    def refresh(self) -> None:
        selected = self.selected()
        identity = selected.id if selected else None
        self.entities = self.catalogue.list_entities(Part)
        self.identification_words: dict[UUID, str] = {}
        if self.host_window.documentation is not None:
            for part in self.entities:
                try:
                    info = self.host_window.documentation.identification(part.id)
                    self.identification_words[part.id] = " ".join(v.value for v in info.values)
                except DomainError:
                    pass  # A damaged optional profile does not hide the local component.

        packages = {p.id: p.name for p in self.catalogue.list_entities(Package)}
        lab_ids = {i.id for i in self.catalogue.list_entities(Inventory) if i.name == "Lab"}
        stocks = self.catalogue.list_entities(StockItem)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.entities))
        for row, part in enumerate(self.entities):
            choices = self.resource_choices(part)
            texts = (
                part.name,
                packages.get(part.package_id, "Non associé") if part.package_id else "Non associé",
                f"{len(choices)}/4 choisis",
                part.state.value,
                str(
                    sum(
                        s.quantity
                        for s in stocks
                        if s.part_id == part.id and s.inventory_id in lab_ids
                    )
                ),
            )
            for column, text in enumerate(texts):
                item = QTableWidgetItem() if column == 4 else QTableWidgetItem(text)
                if column == 4:
                    item.setData(Qt.ItemDataRole.DisplayRole, int(text))
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                item.setData(Qt.ItemDataRole.UserRole, str(part.id))
                item.setToolTip(part.description if column == 0 else text)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, ROW_HEIGHT)
        self.table.sortItems(self.sort_column, self.sort_order)
        by_id = {str(part.id): part for part in self.entities}
        ordered: list[Part] = []
        for row in range(self.table.rowCount()):
            first = self.table.item(row, 0)
            assert first is not None
            ordered.append(by_id[first.data(Qt.ItemDataRole.UserRole)])
        self.entities = ordered
        self.table.horizontalHeader().setSortIndicator(self.sort_column, self.sort_order)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        if identity:
            row = next((i for i, part in enumerate(self.entities) if part.id == identity), -1)
            if row >= 0:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.filter_rows()
        self.show_details()

    def filter_rows(self) -> None:
        query = self.search.text().casefold().strip()
        visible = 0
        for row, part in enumerate(self.entities):
            words = (
                " ".join(
                    item.text()
                    for col in range(self.table.columnCount())
                    if (item := self.table.item(row, col)) is not None
                )
                + " "
                + part.description
                + " "
                + self.identification_words.get(part.id, "")
            )
            hidden = query not in words.casefold() or bool(
                self.state_filter.currentData()
                and part.state.value != self.state_filter.currentData()
            )
            self.table.setRowHidden(row, hidden)
            visible += not hidden
        self.list_stack.setCurrentIndex(0 if visible else 1)
        self.empty.title.setText("Aucun résultat" if self.entities else "Aucun composant")
        self.empty.description.setText(
            "Essayez un autre nom ou effacez la recherche."
            if self.entities
            else "Ajoutez votre première référence pour préparer ses ressources et son stock."
        )
        if self.table.currentRow() >= 0 and self.table.isRowHidden(self.table.currentRow()):
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        self.show_details()

    def show_details(self) -> None:
        part = self.selected()
        identity = part.id if part else None
        changed = identity != self._displayed_part_id
        self._displayed_part_id = identity
        if changed:
            self.message.clear()
        for button in self.selection_actions:
            button.setEnabled(part is not None)
        self.detail_stack.setCurrentIndex(1 if part else 0)
        if part is None:
            return
        self.name.setText(part.name)
        self.description.setText(part.description)
        self.description.setVisible(bool(part.description))
        for value in self.identification_values.values():
            value.setText("—")
        if self.host_window.documentation is not None:
            try:
                info = self.host_window.documentation.identification(part.id)
                for field, value in self.identification_values.items():
                    value.setText(info.value(field) or "—")
                self.identification_text.setText(
                    " · ".join(
                        v.value
                        for v in info.values
                        if v.field.value in ("manufacturer", "mpn", "category") and v.value
                    )
                    or "Identification constructeur non renseignée"
                )
            except DomainError as error:
                self.identification_text.setText(str(error))
        self.badge.set_status(part.state.value)
        package = self.catalogue.require(Package, part.package_id) if part.package_id else None
        self.package_name.setText(
            "Package · " + package.name if package else "! Aucun package associé"
        )
        self.choices = self.resource_choices(part)
        resolver = self.host_window.resolver
        for role, row in self.resource_rows.items():
            choice = self.choices.get(role)
            row.inspect.setEnabled(choice is not None)
            if choice and choice.reference:
                row.set_resource("✓ " + choice.reference.identifier, "Official KiCad", "Changer")
            elif choice and choice.asset_id:
                asset = self.catalogue.require(Asset, choice.asset_id)
                row.set_resource("✓ " + asset.name, origin_label(asset.origin.value), "Changer")
            else:
                owner = package if role in (AssetType.FOOTPRINT, AssetType.MODEL_3D) else part
                associated = (
                    [self.catalogue.require(Asset, identity) for identity in owner.asset_ids]
                    if owner
                    else []
                )
                count = sum(asset.asset_type is role for asset in associated)
                row.set_resource(
                    "! Non sélectionné" + (f" · {count} fichier(s) associé(s)" if count else ""),
                    "Choix à faire",
                    "Choisir"
                    if count
                    else "Ajouter"
                    if role is AssetType.DATASHEET
                    else "Résoudre",
                )
            row.setToolTip(
                "Un choix enregistré ne certifie pas l'intégrité : consultez la validation locale."
            )
            row.action.setEnabled(
                resolver is not None
                and (package is not None or role in (AssetType.SYMBOL, AssetType.DATASHEET))
            )
        missing_names = {
            AssetType.SYMBOL: "symbole",
            AssetType.FOOTPRINT: "footprint",
            AssetType.MODEL_3D: "3D (facultatif)",
            AssetType.DATASHEET: "datasheet (facultative)",
        }
        missing = [name for role, name in missing_names.items() if role not in self.choices]
        self.missing_summary.setText(
            "! À choisir : " + ", ".join(missing)
            if missing
            else "✓ 4 ressources choisies · intégrité à valider"
        )
        stocks = self.catalogue.list_entities(StockItem)
        totals = [
            f"{inventory.name} : "
            + str(
                sum(
                    s.quantity
                    for s in stocks
                    if s.part_id == part.id and s.inventory_id == inventory.id
                )
            )
            for inventory in self.catalogue.list_entities(Inventory)
        ]
        locations = {loc.id: loc.name for loc in self.catalogue.list_entities(Location)}
        places = sorted(
            {
                locations.get(item.location_id, "Sans emplacement")
                if item.location_id
                else "Sans emplacement"
                for item in stocks
                if item.part_id == part.id
            }
        )
        self.stock_text.setText(
            (" · ".join(totals) or "Aucun inventaire")
            + ("\nEmplacements : " + ", ".join(places) if places else "")
        )
        self.stock_summary.setText("Stock · " + " · ".join(totals) if totals else "Aucun stock")
        collections = self.catalogue.list_entities(Collection)
        member_names = [c.name for c in collections if part.id in c.part_ids]
        self.memberships.setText(
            "Présent dans : " + ", ".join(member_names)
            if member_names
            else "Pas encore exposé à KiCad. Ajoutez-le à une bibliothèque, "
            "puis validez et publiez celle-ci."
        )
        selected_collection = self.collections.currentData()
        self.collections.blockSignals(True)
        self.collections.clear()
        for collection in collections:
            self.collections.addItem(collection.name, str(collection.id))
        index = self.collections.findData(selected_collection)
        lab = next((i for i, c in enumerate(collections) if c.name == "LabParts"), 0)
        self.collections.setCurrentIndex(index if index >= 0 else lab)
        self.collections.blockSignals(False)
        self.add_button.setEnabled(bool(collections))
        eligible = False
        qualification_state = "UNCHECKED"
        self.validation_text.setText(
            "Aucun rapport : lancez une validation locale. "
            "La présence de ressources n'atteste pas leur validité."
        )
        if self.host_window.validation:
            try:
                qualification = self.host_window.validation.qualification(part)
                eligible, qualification_state = qualification.eligible, qualification.state
                if qualification.report:
                    self.validation_text.setText(
                        "Rapport obsolète : revalidez après les changements."
                        if qualification.stale
                        else "Rapport actuel · "
                        + qualification.report.created_at
                        + (" · WARNING acceptés" if qualification.report.warnings_accepted else "")
                    )
            except DomainError as error:
                qualification_state = "ERROR"
                self.validation_text.setText(str(error))
        self.qualification_badge.set_status(qualification_state)
        required = package is not None and all(
            role in self.choices for role in (AssetType.SYMBOL, AssetType.FOOTPRINT)
        )
        identified = part.state is PartState.IDENTIFIED
        self.workflow.set_steps(
            identified, required, eligible, bool(member_names), qualification_state
        )
        self.next_action = (
            "identify"
            if not identified
            else "resolve"
            if not required
            else "verify"
            if not eligible
            else "library"
        )
        self.context_button.setText(
            {
                "identify": "Identifier le composant",
                "resolve": "Résoudre les ressources" if package else "Associer un package",
                "verify": "Valider le composant",
                "library": "Ouvrir Bibliothèques"
                if member_names
                else "Ajouter à la bibliothèque sélectionnée",
            }[self.next_action]
        )
        self.context_button.setEnabled(
            (self.next_action != "resolve" or package is None or resolver is not None)
            and (self.next_action != "verify" or self.host_window.validation is not None)
            and part.state is not PartState.DEPRECATED
        )
        if part.state is PartState.DEPRECATED:
            self.context_button.setText("Composant déprécié")
        self.technical.setText(
            f"UUID : {part.id}\nFabricant et MPN : consultez Identification et datasheets.\n"
            "Ressources : choix enregistrés, contrôlés par la validation M5.\n"
            "La publication est effectuée sur une bibliothèque, "
            "sans changer l'état du composant."
        )
        self.update_library_action()
        if changed:
            scroll = self.detail_stack.currentWidget()
            if isinstance(scroll, QScrollArea):
                scroll.verticalScrollBar().setValue(0)

    def edit(self, existing: bool) -> None:
        part = self.selected() if existing else None
        if existing and part is None:
            return
        self.host_window.show_editor(EntityDialog(self.catalogue, Part, part, self))

    def edit_package(self) -> None:
        part = self.selected()
        if part is None:
            return
        if part.package_id:
            package = self.catalogue.require(Package, part.package_id)
            self.host_window.show_editor(EntityDialog(self.catalogue, Package, package, self))
        else:
            self.edit(True)

    def resource_action(self, role: AssetType) -> None:
        part, resolver = self.selected(), self.host_window.resolver
        if part is None or resolver is None:
            return
        if (
            role is AssetType.DATASHEET
            and role not in self.choices
            and self.host_window.imports
            and not any(asset.asset_type is role for asset in self.catalogue.list_entities(Asset))
        ):
            source, _ = QFileDialog.getOpenFileName(
                self, "Importer une datasheet", "", "PDF (*.pdf);;" + FILTER
            )
            if not source:
                return
            if ImportDialog(self.host_window.imports, source).exec() != QDialog.DialogCode.Accepted:
                return
            self.host_window.refresh()
        dialog = self.host_window.resource_dialog(part, self)
        dialog.role.setCurrentIndex(dialog.role.findData(role.value))
        if role is AssetType.DATASHEET:
            dialog.query.clear()
            dialog.search()
        dialog.exec()
        self.host_window.refresh()

    def resolve(self) -> None:
        part, resolver = self.selected(), self.host_window.resolver
        if part and resolver:
            self.host_window.resource_dialog(part, self).exec()
            self.host_window.refresh()

    def validate_local(self) -> None:
        part, validation = self.selected(), self.host_window.validation
        if part and validation:
            ValidationDialog(validation, part, self).exec()
            self.show_details()

    def add_to_library(self) -> None:
        part = self.selected()
        identity = self.collections.currentData()
        if part is None or identity is None:
            return
        try:
            collection = self.catalogue.require(Collection, UUID(identity))
            if part.id in collection.part_ids:
                self.message.setText(f"{part.name} est déjà dans {collection.name}.")
                return
            self.catalogue.save(replace(collection, part_ids=(*collection.part_ids, part.id)))
            self.host_window.refresh()
            self.message.show_message(
                f"{part.name} ajouté à {collection.name}. "
                "Validez la bibliothèque avant de publier.",
                "success",
            )
        except DomainError as error:
            self.message.show_message(str(error), "error")

    def inspect_resource(self, role: AssetType) -> None:
        choice = self.choices.get(role)
        if choice is not None:
            self.host_window.inspect_resource(choice)

    def open_assistance(self) -> None:
        part = self.selected()
        if part is not None:
            self.host_window.open_assistance(part)

    def open_documentation(self) -> None:
        part = self.selected()
        if part is not None:
            self.host_window.open_documentation(part)

    def open_stock(self) -> None:
        part = self.selected()
        if part:
            self.host_window.open_stock(part)

    def advance(self) -> None:
        part = self.selected()
        if part is None:
            return
        if self.next_action == "identify":
            self.edit(True)
        elif self.next_action == "resolve":
            if part.package_id:
                self.resolve()
            else:
                self.edit(True)
        elif self.next_action == "verify":
            self.validate_local()
        elif any(part.id in c.part_ids for c in self.catalogue.list_entities(Collection)):
            self.host_window.open_libraries()
        else:
            self.add_to_library()

    def update_library_action(self) -> None:
        if self.next_action == "library" and self.selected():
            part = self.selected()
            assert part is not None
            included = any(part.id in c.part_ids for c in self.catalogue.list_entities(Collection))
            self.context_button.setText(
                "Ouvrir Bibliothèques"
                if included
                else "Ajouter à " + (self.collections.currentText() or "une bibliothèque")
            )
