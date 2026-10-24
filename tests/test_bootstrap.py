"""Package, installed entry points and offline Qt startup checks."""

import os
import subprocess
import sys
import sysconfig
from importlib.metadata import distribution
from pathlib import Path

import kipartmanager


def test_package_version_matches_distribution() -> None:
    assert kipartmanager.__version__ == distribution("kipartmanager").version


def test_installed_console_entry_point() -> None:
    entry = next(
        item
        for item in distribution("kipartmanager").entry_points
        if item.group == "console_scripts" and item.name == "kipartmanager"
    )
    assert callable(entry.load())
    executable = Path(sysconfig.get_path("scripts")) / (
        "kipartmanager.exe" if sys.platform == "win32" else "kipartmanager"
    )
    result = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert result.stdout.strip() == f"kipartmanager {kipartmanager.__version__}"


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "kipartmanager", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert result.stdout.strip() == f"kipartmanager {kipartmanager.__version__}"


def test_offline_imports_and_qt_startup(tmp_path: Path) -> None:
    # Isolate Qt's singleton and native plugin initialization from the pytest process.
    script = """
import socket
import sys

def forbidden(*args, **kwargs):
    raise AssertionError("Network access attempted during startup")

socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden

import kipartmanager
import kipartmanager.application
import kipartmanager.domain
import kipartmanager.ports
import kipartmanager.infrastructure
assert "PySide6" not in sys.modules

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel
from kipartmanager.bootstrap import main
from kipartmanager.ui.main_window import MainWindow

verified = []
def inspect_and_close():
    app = QApplication.instance()
    assert app is not None
    windows = [widget for widget in app.topLevelWidgets() if isinstance(widget, MainWindow)]
    assert len(windows) == 1
    window = windows[0]
    assert window.isVisible()
    assert window.windowTitle() == "FabParts"
    assert not app.windowIcon().isNull()
    assert not window.windowIcon().isNull()
    assert app.desktopFileName() == "kipartmanager"
    assert app.applicationName() == "KiPart Manager"  # Existing data path remains stable.
    assert app.applicationDisplayName() == "FabParts"
    assert any(label.text() == "Electronic component manager"
               for label in window.findChildren(QLabel))
    logo = window.findChild(QLabel, "applicationLogo")
    assert logo is not None and not logo.pixmap().isNull()
    assert window.tabs.count() == 6
    assert any("FabParts" in label.text() for label in window.findChildren(QLabel))
    assert window.navigation.count() == 6
    verified.append(True)
    window.close()

original_show = MainWindow.show
def show_and_schedule_check(self):
    original_show(self)
    QTimer.singleShot(200, inspect_and_close)

MainWindow.show = show_and_schedule_check
assert main(["--data-dir", sys.argv[1]]) == 0
assert verified == [True]
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
