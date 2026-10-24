"""Small M1 entity editors; all persistence goes through application use cases."""

from typing import cast
from uuid import UUID, uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from kipartmanager.application.catalogue import Catalogue
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    DomainError,
    Entity,
    Inventory,
    Location,
    Package,
    Part,
    PartState,
    StockItem,
)
from kipartmanager.ui.components import (
    Disclosure,
    MessageBanner,
    PageHeader,
    PageLayout,
    ScrollPanel,
    label,
    primary,
)
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.icons import icon
from kipartmanager.ui.theme import COLORS, M


class EntityDialog(QDialog):
    def __init__(
        self,
        catalogue: Catalogue,
        kind: type[Entity],
        entity: Entity | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.catalogue, self.kind, self.entity = catalogue, kind, entity
        title = {
            Part: "Composant",
            Package: "Package",
            Asset: "Ressource",
            StockItem: "Stock",
            Inventory: "Inventaire",
            Location: "Emplacement",
            Collection: "Bibliothèque",
        }[kind]
        self.setWindowTitle(
            ("Modifier — " if entity else "Créer — ")
            + title
            + (" · " + getattr(entity, "name", "") if entity else "")
        )
        self.resize(520, 450)
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                title,
                "* Champs requis · les choix de ressources restent explicites.",
            )
        )
        help_key = {
            Part: "symbol",
            Package: "package",
            Asset: "asset",
            Inventory: "inventory",
            StockItem: "inventory",
            Collection: "library",
        }.get(kind)
        if help_key:
            help_section = Disclosure("Aide contextuelle", HELP[help_key])
            help_section.body.addWidget(label(HELP[help_key]))
            layout.addWidget(help_section)
        fields = QWidget()
        form = QFormLayout(fields)
        scroll = ScrollPanel(fields)
        form.setHorizontalSpacing(M)
        form.setVerticalSpacing(M)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addWidget(scroll, 1)
        self.name = QLineEdit(getattr(entity, "name", ""))
        self.description = QLineEdit(getattr(entity, "description", ""))
        self.source = QLineEdit(entity.source if isinstance(entity, Asset) else "")
        self.quantity = QLineEdit(str(entity.quantity if isinstance(entity, StockItem) else 0))
        self.quantity.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.quantity.setAccessibleName("Quantité possédée")
        self.quantity.setToolTip("Nombre entier positif ou nul de composants dans cet inventaire.")
        self.combos: dict[str, QComboBox] = {}
        self.members = QListWidget()
        self.members.setMinimumHeight(80)
        self.members.setMaximumHeight(180)
        form.addRow(
            label("QUANTITÉS ET EMPLACEMENT" if kind is StockItem else "IDENTITÉ", "section")
        )
        if kind is not StockItem:
            form.addRow("Nom *", self.name)
        if kind in (Part, Package):
            form.addRow("Description", self.description)
        if kind is Part:
            self._reference(
                form,
                "package",
                "Package",
                Package,
                entity.package_id if isinstance(entity, Part) else None,
                optional=True,
            )
            self._choice(
                form,
                "state",
                "État",
                [state.value for state in PartState],
                entity.state.value if isinstance(entity, Part) else "DRAFT",
            )
        if kind is Part:
            self.combos["package"].setToolTip(HELP["package"])
        if kind is Asset:
            form.addRow(label("Validation sémantique : UNCHECKED."))
            if isinstance(entity, Asset) and entity.file is not None:
                form.addRow(label(f"{entity.file.original_name}\nSHA-256 : {entity.file.sha256}"))
            self._choice(
                form,
                "type",
                "Type",
                [value.value for value in AssetType],
                entity.asset_type.value if isinstance(entity, Asset) else "SYMBOL",
            )
            self._choice(
                form,
                "origin",
                "Provenance",
                [value.value for value in AssetOrigin],
                entity.origin.value if isinstance(entity, Asset) else "USER_PROVIDED",
            )
            form.addRow("Source / référence", self.source)
        if kind is StockItem:
            self._reference(
                form,
                "part",
                "Composant",
                Part,
                entity.part_id if isinstance(entity, StockItem) else None,
            )
            self._reference(
                form,
                "inventory",
                "Inventaire",
                Inventory,
                entity.inventory_id if isinstance(entity, StockItem) else None,
            )
            self._reference(
                form,
                "location",
                "Localisation",
                Location,
                entity.location_id if isinstance(entity, StockItem) else None,
                optional=True,
            )
            form.addRow("Quantité *", self.quantity)
        if kind in (Part, Package, Collection):
            selected = (
                entity.part_ids
                if isinstance(entity, Collection)
                else getattr(entity, "asset_ids", ())
            )
            candidates: list[Part | Asset]
            if kind is Collection:
                candidates = list(catalogue.list_entities(Part))
            else:
                allowed = (
                    {AssetType.SYMBOL, AssetType.DATASHEET}
                    if kind is Part
                    else {AssetType.FOOTPRINT, AssetType.MODEL_3D}
                )
                candidates = [
                    asset for asset in catalogue.list_entities(Asset) if asset.asset_type in allowed
                ]
            for candidate in candidates:
                item = QListWidgetItem(candidate.name)
                item.setToolTip(candidate.name)
                item.setData(Qt.ItemDataRole.UserRole, str(candidate.id))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if candidate.id in selected else Qt.CheckState.Unchecked
                )
                self.members.addItem(item)
            associations = Disclosure(
                "Composants inclus" if kind is Collection else "Fichiers associés",
                "Une association ne remplace pas un choix de ressource.",
            )
            associations.body.addWidget(self.members)
            if kind is not Collection:
                associations.body.addWidget(
                    label("Associer un fichier ne le choisit pas pour KiCad.")
                )
            form.addRow(associations)
        self.error = MessageBanner()
        self.error.setProperty("tone", "error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        primary(buttons.button(QDialogButtonBox.StandardButton.Save))
        buttons.button(QDialogButtonBox.StandardButton.Save).setIcon(
            icon("check", color=COLORS["PRIMARY_TEXT"])
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        layout.addWidget(buttons)

    def _reference(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        kind: type[Entity],
        current: UUID | None,
        *,
        optional: bool = False,
    ) -> None:
        combo = QComboBox()
        if optional:
            combo.addItem("Aucun", None)
        for entity in self.catalogue.list_entities(kind):
            combo.addItem(getattr(entity, "name", ""), str(entity.id))
        index = combo.findData(str(current) if current is not None else None)
        if index >= 0:
            combo.setCurrentIndex(index)
        self.combos[key] = combo
        form.addRow(label, combo)

    def _choice(
        self, form: QFormLayout, key: str, label: str, values: list[str], current: str
    ) -> None:
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(current)
        self.combos[key] = combo
        form.addRow(label, combo)

    def _identity(self, key: str, *, optional: bool = False) -> UUID | None:
        value = self.combos[key].currentData()
        if value is None and not optional:
            raise DomainError(
                "Créer et sélectionner les références obligatoires avant d'enregistrer."
            )
        return UUID(str(value)) if value is not None else None

    def _quantity(self) -> int:
        try:
            return int(self.quantity.text())
        except ValueError as error:
            raise DomainError("La quantité doit être un entier positif ou nul.") from error

    def build_entity(self) -> Entity:
        identity = self.entity.id if self.entity else uuid4()
        members_list: list[UUID] = []
        for index in range(self.members.count()):
            item = self.members.item(index)
            assert item is not None
            if item.checkState() == Qt.CheckState.Checked:
                members_list.append(UUID(str(item.data(Qt.ItemDataRole.UserRole))))
        members = tuple(members_list)
        if self.kind is Part:
            return Part(
                id=identity,
                name=self.name.text(),
                description=self.description.text(),
                package_id=self._identity("package", optional=True),
                asset_ids=members,
                state=PartState(self.combos["state"].currentText()),
            )
        if self.kind is Package:
            return Package(
                id=identity,
                name=self.name.text(),
                description=self.description.text(),
                asset_ids=members,
            )
        if self.kind is Asset:
            return Asset(
                id=identity,
                name=self.name.text(),
                asset_type=AssetType(self.combos["type"].currentText()),
                origin=AssetOrigin(self.combos["origin"].currentText()),
                source=self.source.text(),
                file=self.entity.file if isinstance(self.entity, Asset) else None,
                provenance=self.entity.provenance if isinstance(self.entity, Asset) else None,
            )
        if self.kind is Collection:
            return Collection(id=identity, name=self.name.text(), part_ids=members)
        if self.kind is Inventory:
            return Inventory(id=identity, name=self.name.text())
        if self.kind is Location:
            return Location(id=identity, name=self.name.text())
        return StockItem(
            id=identity,
            part_id=cast(UUID, self._identity("part")),
            inventory_id=cast(UUID, self._identity("inventory")),
            location_id=self._identity("location", optional=True),
            quantity=self._quantity(),
        )

    def save(self) -> None:
        try:
            self.catalogue.save(self.build_entity())
        except DomainError as error:
            self.error.show_message(str(error), "error")
            return
        self.accept()
