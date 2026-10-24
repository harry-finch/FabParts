"""Professional Workshop: one dark palette, compact spacing and shared controls."""

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

XS = 4
S = 8
M = 12
L = 16
XL = 24
ROW_HEIGHT = 32
CONTROL_HEIGHT = 30
SIDEBAR_WIDTH = 176

COLORS = {
    "BG": "#1e1e1e",
    "CHROME": "#191919",
    "BUTTON": "#292929",
    "DIVIDER": "#2d2d2d",
    "SCROLL": "#555555",
    "PANEL": "#232323",
    "CONTROL": "#171717",
    "HOVER": "#303030",
    "LINE": "#3b3b3b",
    "TEXT": "#e3e3e3",
    "MUTED": "#ababab",
    "DISABLED": "#777777",
    "ACCENT": "#E8B954",
    "PRIMARY": "#E8B954",
    "PRIMARY_HOVER": "#F0C66A",
    "PRIMARY_PRESSED": "#DCA844",
    "PRIMARY_TEXT": "#202226",
    "SELECTION": "#3B3425",
    "INFO": "#579edb",
    "SUCCESS": "#83c9a4",
    "WARNING": "#e8b76c",
    "ERROR": "#f09595",
    "IDENTITY": "#E8B954",
}

QSS = """
QWidget { color: @TEXT@; font-size: 12px; }
QMainWindow, QDialog { background: @BG@; }
QWidget#sidebar { background: @PANEL@; border-right: 1px solid @LINE@; }
QLabel[role="title"] { font-size: 18px; font-weight: 600; }
QLabel[role="heading"] { font-size: 13px; font-weight: 600; }
QLabel[role="section"] { font-size: 11px; font-weight: 600; color: @MUTED@; }
QLabel[role="muted"] { color: @MUTED@; }
QLabel[role="brand"] { font-size: 16px; font-weight: 600; color: @TEXT@; }
QWidget#topbar { background: @CHROME@; border-top: 2px solid @IDENTITY@;
 border-bottom: 1px solid @LINE@; }
QStatusBar { background: @CHROME@; color: @MUTED@; border-top: 1px solid @LINE@; }
QStatusBar QLabel { color: @MUTED@; padding: 3px 8px; font-size: 11px; }
QStatusBar::item { border: none; }
QFrame[role="card"] { background: @PANEL@; border: none; border-top: 1px solid @LINE@;
 border-radius: 0; }
QPushButton { background: @BUTTON@; border: 1px solid @LINE@; border-radius: 3px;
 padding: 4px 8px; min-height: 18px; }
QPushButton:enabled:hover { background: @HOVER@; border-color: @MUTED@; }
QPushButton:enabled:pressed { background: @SELECTION@; }
QPushButton[role="primary"] { background: @PRIMARY@; border-color: @PRIMARY@;
 color: @PRIMARY_TEXT@; font-weight: 600; }
QPushButton[role="primary"]:enabled:hover {
 background: @PRIMARY_HOVER@; border-color: @PRIMARY_HOVER@; }
QPushButton[role="primary"]:enabled:pressed {
 background: @PRIMARY_PRESSED@; border-color: @PRIMARY_PRESSED@; }
QPushButton[role="quiet"] { background: transparent; border-color: transparent;
 color: @MUTED@; text-align: left; }
QPushButton[role="quiet"]:enabled:hover {
 background: @HOVER@; color: @TEXT@; }
QPushButton[role="quiet"]:enabled:checked {
 background: @SELECTION@; color: @ACCENT@; }
QPushButton[role="destructive"] { color: @ERROR@; }
QPushButton:disabled { color: @DISABLED@; background: @PANEL@; border-color: @LINE@; }
QPushButton:focus { border-color: @ACCENT@; }
QPushButton[role="primary"]:enabled:focus { border-color: @PRIMARY_TEXT@; }
QPushButton[role="primary"]:disabled, QPushButton[role="quiet"]:disabled {
 color: @DISABLED@; background: @PANEL@; border-color: @LINE@; }
QLineEdit, QComboBox, QSpinBox { background: @CONTROL@; border: 1px solid @LINE@;
 border-radius: 3px; padding: 4px 7px; min-height: 18px;
 selection-background-color: @SELECTION@; selection-color: @TEXT@; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @ACCENT@; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: @DISABLED@; }
QComboBox QAbstractItemView { background: @CONTROL@; color: @TEXT@;
 selection-background-color: @SELECTION@; selection-color: @TEXT@; }
QSpinBox { padding-right: 24px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
 width: 20px; border: none; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
 width: 20px; border: none; }
QSpinBox::up-arrow { image: url("@CHEVRONUP@"); width: 12px; height: 8px; }
QSpinBox::down-arrow { image: url("@CHEVRON@"); width: 12px; height: 8px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: url("@CHEVRON@"); width: 12px; height: 8px; }
QCheckBox { spacing: 6px; padding: 2px 0; }
QCheckBox::indicator, QListWidget::indicator { width: 14px; height: 14px;
 border: 1px solid @MUTED@; border-radius: 2px; background: @CONTROL@; }
QCheckBox::indicator:checked, QListWidget::indicator:checked {
 background: @SELECTION@; border-color: @ACCENT@; image: url("@CHECK@"); }
QCheckBox:focus { color: @ACCENT@; }
QCheckBox::indicator:disabled, QListWidget::indicator:disabled {
 background: @PANEL@; border-color: @LINE@; }
QListWidget { background: @PANEL@; border: 1px solid @LINE@; border-radius: 3px;
 padding: 3px; outline: none; }
QListWidget::item { padding: 5px 7px; border: 1px solid transparent; border-radius: 2px; }
QListWidget::item:hover { background: @HOVER@; }
QListWidget::item:selected { background: @SELECTION@; border-color: @ACCENT@; color: @TEXT@; }
QListWidget:focus { border-color: @ACCENT@; }
QListWidget#navigation { background: transparent; border: none; padding: 0; }
QListWidget#navigation::item { padding: 7px 5px; margin: 1px 0; }
QListWidget#navigation::item:selected { background: @SELECTION@;
 border-color: transparent; border-left: 2px solid @ACCENT@; font-weight: 600; }
QTableWidget { background: @PANEL@; alternate-background-color: @PANEL@;
 border: 1px solid @LINE@; border-radius: 3px; padding: 3px; outline: none;
 selection-background-color: @SELECTION@; selection-color: @TEXT@; }
QTableWidget::item { padding: 3px 6px; border: none; border-bottom: 1px solid @DIVIDER@; }
QTableWidget::item:hover { background: @HOVER@; }
QTableWidget::item:selected { background: @SELECTION@; color: @TEXT@; }
QTableWidget:focus { border-color: @ACCENT@; }
QHeaderView::section { background: @PANEL@; color: @MUTED@; font-weight: 600;
 padding: 6px; border: none; border-bottom: 1px solid @LINE@; }
QTableCornerButton::section { background: @PANEL@; border: none; }
QTabWidget::pane { border: none; border-top: 1px solid @LINE@; }
QTabBar { qproperty-drawBase: false; }
QTabBar::tab { background: transparent; color: @MUTED@; padding: 7px 10px;
 border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @TEXT@; border-bottom-color: @ACCENT@; font-weight: 600; }
QTabBar::tab:hover { background: @HOVER@; }
QTextEdit { background: transparent; color: @TEXT@; border: none; padding: 0;
 selection-background-color: @SELECTION@; selection-color: @TEXT@; }
QTextEdit[readOnly="false"] { background: @CONTROL@; border: 1px solid @LINE@;
 border-radius: 3px; padding: 6px; }
QTextEdit:focus { border-color: @ACCENT@; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
QScrollBar::handle { background: @SCROLL@; border-radius: 3px; }
QScrollBar::handle:vertical { min-height: 24px; }
QScrollBar::handle:horizontal { min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: @LINE@; width: 1px; }
QSplitter::handle:hover { background: @ACCENT@; }
QProgressBar { border: none; border-radius: 2px; background: @CONTROL@; max-height: 5px; }
QProgressBar::chunk { background: @ACCENT@; }
QLabel[role="badge"] { padding: 1px 0; background: transparent;
 color: @MUTED@; font-weight: 400; }
QLabel[role="badge"][tone="success"] { color: @SUCCESS@; font-weight: 600; }
QLabel[role="badge"][tone="warning"] { color: @WARNING@; font-weight: 600; }
QLabel[role="badge"][tone="error"] { color: @ERROR@; font-weight: 600; }
QLabel[role="badge"][tone="info"] { color: @MUTED@; }
QLabel[role="message"] { padding: 5px 8px; background: transparent;
 border-left: 2px solid @INFO@; color: @MUTED@; }
QLabel[role="message"][tone="error"] { color: @ERROR@; border-color: @ERROR@; }
QLabel[role="message"][tone="warning"] { color: @WARNING@; border-color: @WARNING@; }
QLabel[role="message"][tone="success"] { color: @SUCCESS@; border-color: @SUCCESS@; }
QLabel[role="workflow"][tone="complete"] { color: @SUCCESS@; }
QLabel[role="workflow"][tone="current"] { color: @TEXT@; font-weight: 600; }
QLabel[role="workflow"][tone="pending"] { color: @DISABLED@; }
QMenu { background: @PANEL@; border: 1px solid @LINE@; padding: 4px; }
QMenu::item { padding: 5px 20px; }
QMenu::item:selected { background: @SELECTION@; }
QMenu::item:disabled { color: @DISABLED@; }
QToolTip { color: @TEXT@; background: @CONTROL@; border: 1px solid @LINE@;
 padding: 5px; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = app.style().standardPalette()
    for role, color in (
        (QPalette.ColorRole.Window, COLORS["BG"]),
        (QPalette.ColorRole.WindowText, COLORS["TEXT"]),
        (QPalette.ColorRole.Base, COLORS["CONTROL"]),
        (QPalette.ColorRole.AlternateBase, COLORS["PANEL"]),
        (QPalette.ColorRole.Text, COLORS["TEXT"]),
        (QPalette.ColorRole.Button, COLORS["CONTROL"]),
        (QPalette.ColorRole.ButtonText, COLORS["TEXT"]),
        (QPalette.ColorRole.Highlight, COLORS["SELECTION"]),
        (QPalette.ColorRole.HighlightedText, COLORS["TEXT"]),
        (QPalette.ColorRole.ToolTipBase, COLORS["CONTROL"]),
        (QPalette.ColorRole.ToolTipText, COLORS["TEXT"]),
        (QPalette.ColorRole.Link, COLORS["ACCENT"]),
        (QPalette.ColorRole.LinkVisited, COLORS["PRIMARY_PRESSED"]),
        (QPalette.ColorRole.Accent, COLORS["ACCENT"]),
        (QPalette.ColorRole.PlaceholderText, COLORS["MUTED"]),
    ):
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["DISABLED"]))
    app.setPalette(palette)
    icons = Path(__file__).parent / "icons"
    style = QSS
    for key, color in COLORS.items():
        style = style.replace(f"@{key}@", color)
    app.setStyleSheet(
        style.replace("@CHEVRONUP@", (icons / "chevron-up.svg").as_posix())
        .replace("@CHEVRON@", (icons / "chevron.svg").as_posix())
        .replace("@CHECK@", (icons / "check.svg").as_posix())
    )


PREVIEW_COLORS = {
    "Background": "#25282d",
    "Fill": "#343a43",
    "Body": "#d5dbe5",
    "Pins": "#7cb8e8",
    "Pads": "#c9984d",
    "Pad1": "#da8175",
    "PadLabel": "#202226",
    "Drill": "#25282d",
    "F.SilkS": "#7cb8e8",
    "B.SilkS": "#7cb8e8",
    "F.Fab": "#a8b1be",
    "B.Fab": "#a8b1be",
    "F.CrtYd": "#baa1d0",
    "B.CrtYd": "#baa1d0",
    "Other": "#a8b1be",
}
