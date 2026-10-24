"""Small presentation primitives shared by pages and workflow dialogs."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QResizeEvent, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from kipartmanager.ui.icons import icon
from kipartmanager.ui.theme import XS, L, M, S


def label(text: str, role: str = "muted") -> QLabel:
    widget = QLabel(text)
    widget.setProperty("role", role)
    widget.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def primary(button: QPushButton) -> QPushButton:
    button.setProperty("role", "primary")
    return button


def quiet(button: QPushButton) -> QPushButton:
    button.setProperty("role", "quiet")
    return button


class Disclosure(QWidget):
    """One compact disclosure for secondary properties; content stays in its layout."""

    def __init__(self, title: str, description: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(XS)
        self.toggle = quiet(QPushButton(title))
        self.toggle.setIcon(icon("chevron-right"))
        self.toggle.setCheckable(True)
        self.toggle.setToolTip(description or title)
        layout.addWidget(self.toggle)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(S, XS, 0, XS)
        self.body.setSpacing(S)
        layout.addWidget(self.content)
        self.content.hide()
        self.toggle.toggled.connect(self.content.setVisible)
        self.toggle.toggled.connect(
            lambda checked: self.toggle.setIcon(
                icon("chevron-down" if checked else "chevron-right")
            )
        )


class PageLayout(QVBoxLayout):
    """Shared page/dialog margins and vertical rhythm, preserving existing layouts."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setContentsMargins(L, L, L, L)
        self.setSpacing(M)


class ScrollPanel(QScrollArea):
    """Resizable, frameless container for existing cards or form fields."""

    def __init__(self, content: QWidget) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content_layout = content.layout()
        if content_layout is not None:
            content_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setWidget(content)


class PageHeader(QWidget):
    def __init__(self, title: str, description: str, action: QPushButton | None = None) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(M)
        words = QVBoxLayout()
        words.setSpacing(XS)
        words.addWidget(label(title, "title"))
        # Longer educational copy belongs in help, not a permanent page paragraph.
        if description:
            if len(description) <= 100:
                words.addWidget(label(description))
            else:
                help_button = quiet(QPushButton("À propos de cette vue"))
                help_button.setIcon(icon("info"))
                help_button.setCheckable(True)
                help_button.setToolTip(description)
                help_text = label(description)
                help_text.hide()
                help_button.toggled.connect(help_text.setVisible)
                words.addWidget(help_button, 0, Qt.AlignmentFlag.AlignLeft)
                words.addWidget(help_text)
        layout.addLayout(words, 1)
        if action:
            if not action.property("role"):
                primary(action)
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)


class StatusBadge(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.setProperty("role", "badge")
        self.set_status(text)

    def set_status(self, text: str) -> None:
        self.setText(text)
        tone = (
            "success"
            if text in {"PASS", "VALIDATED", "PUBLISHED"}
            else "warning"
            if text in {"WARNING", "STALE"}
            else "error"
            if text == "ERROR"
            else "info"
            if text in {"IDENTIFIED", "KICAD_OFFICIAL", "Official KiCad", "Managed"}
            else "neutral"
        )
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setVisible(bool(text))


class MessageBanner(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setProperty("role", "message")
        self.hide()

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setProperty("tone", "info")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setMinimumHeight(self.message_height(max(self.width(), 300)))
        self.updateGeometry()
        self.setVisible(bool(text))

    def message_height(self, width: int) -> int:
        if not self.text():
            return 0
        bounds = self.fontMetrics().boundingRect(
            QRect(0, 0, max(80, width - 16), 100000),
            int(Qt.TextFlag.TextWordWrap),
            self.text(),
        )
        return bounds.height() + 12

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        height = self.message_height(event.size().width())
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)

    def clear(self) -> None:
        self.setText("")

    def show_message(self, text: str, tone: str = "info") -> None:
        self.setText(text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class SearchBar(QLineEdit):
    def __init__(self, placeholder: str = "Rechercher dans cette liste…") -> None:
        super().__init__()
        self.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setAccessibleName(placeholder)


class SectionCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setProperty("role", "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(M, M, M, M)
        self.body.setSpacing(S)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        if title:
            self.body.addWidget(label(title.upper(), "section"))


class EmptyState(QWidget):
    def __init__(self, title: str, description: str, action: QPushButton | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(L, L, L, L)
        layout.addStretch()
        self.title = label(title, "heading")
        self.description = label(description)
        for widget in (self.title, self.description):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(widget)
        if action:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()


class DetailText(QTextEdit):
    """Selectable metadata with safe plain text and wrapping even for long hashes."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setText(text)

    def setText(self, text: str) -> None:
        self.setPlainText(text)


class ResourceRow(QWidget):
    """A named resource, explicit availability, provenance and a next action."""

    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, XS, 0, XS)
        layout.setHorizontalSpacing(S)
        layout.setVerticalSpacing(2)
        self.title = label(title, "muted")
        layout.addWidget(self.title, 0, 0)
        self.action = quiet(QPushButton())
        layout.addWidget(self.action, 0, 1)
        self.inspect = quiet(QPushButton())
        self.inspect.setIcon(icon("eye"))
        self.inspect.setToolTip("Inspecter cette ressource sans changer le choix")
        self.inspect.setAccessibleName("Inspecter " + title)
        self.inspect.hide()
        self.inspect.setEnabled(False)
        layout.addWidget(self.inspect, 0, 2)
        self.name = label("", "body")
        layout.addWidget(self.name, 1, 0, 1, 3)
        self.origin = StatusBadge()
        layout.addWidget(self.origin, 2, 0, 1, 3)
        layout.setColumnStretch(0, 1)

    def set_resource(self, name: str, origin: str, action: str) -> None:
        self.name.setText(name)
        self.origin.set_status(origin if origin != "Choix à faire" else "")
        self.action.setText(action)


class WorkflowStrip(QWidget):
    """Display progress without adding states or publication rules to Part."""

    def __init__(self) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, S, 0, S)
        layout.setSpacing(XS)
        self.identity = label("")
        self.resources = label("")
        self.validation = label("")
        self.publication = label("")
        self.indicators: list[QLabel] = []
        for index, step in enumerate(
            (self.identity, self.resources, self.validation, self.publication)
        ):
            row = QHBoxLayout()
            row.setSpacing(XS)
            indicator = QLabel()
            indicator.setFixedSize(14, 14)
            self.indicators.append(indicator)
            row.addWidget(indicator)
            step.setProperty("role", "workflow")
            row.addWidget(step, 1)
            layout.addLayout(row, index // 2, index % 2)

    def set_steps(
        self,
        identified: bool,
        resolved: bool,
        verified: bool,
        included: bool,
        qualification: str = "UNCHECKED",
    ) -> None:
        self.identity.setText("IDENTIFY")
        steps = (self.identity, self.resources, self.validation, self.publication)
        complete = (identified, resolved, verified, False)
        current = next((i for i, done in enumerate(complete) if not done), 3)
        for i, (step, done) in enumerate(zip(steps, complete, strict=True)):
            tone = "complete" if done else "current" if i == current else "pending"
            step.setProperty("tone", tone)
            step.style().unpolish(step)
            step.style().polish(step)
            self.indicators[i].setPixmap(icon("check" if done else "chevron-right").pixmap(14, 14))
        self.identity.setToolTip("Identité : état du composant IDENTIFIED.")
        self.resources.setText("RESOLVE")
        self.resources.setToolTip(
            "Package associé, symbole et footprint choisis. Intégrité à valider."
        )
        self.validation.setText("VERIFY · " + qualification)
        self.validation.setToolTip("Rapport local actuel et admissible selon les règles M5.")
        self.publication.setText("PUBLISH")
        self.publication.setToolTip(
            "Publier la bibliothèque depuis Bibliothèques. L'appartenance ne vaut pas publication."
            if included
            else "Ajouter à une bibliothèque, puis valider et publier celle-ci."
        )


def origin_label(origin: str) -> str:
    return {
        "KICAD_OFFICIAL": "Official KiCad",
        "USER_PROVIDED": "User provided",
        "MANAGED_LIBRARY": "Managed",
        "MANUFACTURER": "Fabricant",
        "TRUSTED_THIRD_PARTY": "Tiers de confiance",
        "GENERATED_PARAMETRIC": "Généré · paramétrique",
        "GENERATED_AI": "Généré · IA",
    }.get(origin, origin)
