"""M2 desktop import/attach/retrieve controls, using application use cases."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.domain.entities import AssetOrigin, DomainError
from kipartmanager.ui.components import MessageBanner, PageHeader, PageLayout, label, primary
from kipartmanager.ui.context_help import HELP
from kipartmanager.ui.theme import M

FILTER = "Assets (*.pdf *.PDF *.step *.STEP *.stp *.STP *.wrl *.WRL *.kicad_mod *.kicad_sym)"


class ImportDialog(QDialog):
    def __init__(self, imports: AssetImports, source: str) -> None:
        super().__init__()
        self.imports, self.source = imports, source
        self.setWindowTitle("Importer un fichier")
        self.resize(600, 300)
        layout = PageLayout(self)
        layout.addWidget(PageHeader("Importer une ressource", HELP["asset"]))
        form = QFormLayout()
        form.setHorizontalSpacing(M)
        form.setVerticalSpacing(M)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(label(source))
        self.name = QLineEdit()
        self.origin = QComboBox()
        self.origin.addItems([origin.value for origin in AssetOrigin])
        self.origin.setToolTip(
            "La provenance décrit l’origine du fichier, indépendamment de son stockage local."
        )
        self.reference = QLineEdit(source)
        form.addRow("Nom (facultatif)", self.name)
        form.addRow("Provenance", self.origin)
        form.addRow("Référence/source", self.reference)
        layout.addLayout(form)
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
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.imports.import_file(
                self.source,
                name=self.name.text(),
                origin=AssetOrigin(self.origin.currentText()),
                source_reference=self.reference.text(),
            )
        except DomainError as error:
            self.error.show_message(str(error), "error")
            return
        self.accept()
