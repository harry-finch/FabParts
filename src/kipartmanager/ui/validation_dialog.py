"""Scoped checks and explicit acknowledgement of warnings, without publication."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QWidget,
)

from kipartmanager.application.validation import LocalValidation
from kipartmanager.domain.entities import Collection, DomainError, Part
from kipartmanager.domain.validation import Qualification
from kipartmanager.ui.components import MessageBanner, PageHeader, PageLayout, StatusBadge, primary


class ValidationDialog(QDialog):
    def __init__(
        self, service: LocalValidation, subject: Part | Collection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service, self.subject = service, subject
        self.setWindowTitle(f"Validation locale — {subject.name}")
        self.resize(800, 650)
        layout = PageLayout(self)
        layout.addWidget(
            PageHeader(
                "Validation locale", "Examiner les contrôles de la sélection et leurs limites."
            )
        )
        layout.addWidget(
            QLabel(
                "Contrôles M5 : intégrité, structure KiCad, pins/pads ; géométrie 3D non certifiée."
            )
        )
        self.badge = StatusBadge()
        layout.addWidget(self.badge)
        self.status = MessageBanner()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.items = QListWidget()
        self.items.setWordWrap(True)
        layout.addWidget(self.items)
        self.accept_warnings = QCheckBox("J'ai examiné et j'accepte les WARNING de ce rapport")
        layout.addWidget(self.accept_warnings)
        self.validate_button = QPushButton("Exécuter les contrôles locaux")
        self.validate_button.clicked.connect(self.validate)
        layout.addWidget(primary(self.validate_button))
        self.refresh_button = QPushButton("Vérifier si le rapport est toujours actuel")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.refresh()

    def display(self, qualification: Qualification) -> None:
        self.badge.set_status(qualification.state)
        self.items.clear()
        report = qualification.report
        self.status.setText(
            f"État : {qualification.state} — éligibilité aux contrôles M5 : "
            f"{'oui' if qualification.eligible else 'non'}"
        )
        if report is not None:
            self.status.setText(
                self.status.text() + f"\n{report.created_at} — règles {report.ruleset}\n"
                f"Empreinte : {report.fingerprint}"
            )
            for finding in report.findings:
                self.items.addItem(
                    f"{finding.level.value} — {finding.code.rsplit(':', 1)[-1]} : "
                    f"{finding.message}\n"
                    f"{finding.resource_key}\nSHA-256 : {finding.sha256 or 'sans fichier'}"
                )
        self.accept_warnings.setChecked(False)

    def refresh(self) -> None:
        try:
            self.display(self.service.qualification(self.subject))
        except DomainError as error:
            self.status.show_message(str(error), "error")

    def validate(self) -> None:
        try:
            if self.accept_warnings.isChecked():
                previous = self.service.qualification(self.subject)
                if previous.report is None or previous.stale:
                    raise DomainError(
                        "Exécuter et examiner un rapport actuel avant d'accepter ses WARNING."
                    )
            report = self.service.validate(
                self.subject, accept_warnings=self.accept_warnings.isChecked()
            )
            self.display(self.service.qualification(self.subject))
            if report.level.value == "ERROR":
                self.status.setText(
                    self.status.text() + "\nERROR bloque la qualification de la collection."
                )
        except DomainError as error:
            self.status.show_message(str(error), "error")
