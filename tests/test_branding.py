"""Approved sources, desktop containers and Qt loading without a development cwd."""

import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/kipartmanager/ui/branding"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def test_approved_sources_unchanged() -> None:
    hashes = {
        "symbol.svg": "f9338fce7b32a705f17381e9680de0f1bc6556595717881ff2d80ade665cf06c",
        "app_icon.svg": "46e0d3e144965c1ac6505b07c69708f8acbb22b164a20c5390e5876cd89ff483",
        "lockup_kipart_manager.svg": (
            "df83511120a81f52d69f4c7b8652fd6375c22c9add112e0bb3162dba40eace30"
        ),
    }
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / "source" / name).read_bytes()).hexdigest() == digest


def test_desktop_containers() -> None:
    ico = (ROOT / "app/kipart-icon.ico").read_bytes()
    assert struct.unpack_from("<HHH", ico) == (0, 1, 7)
    for index, size in enumerate(SIZES[:7]):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", ico, 6 + index * 16
        )
        assert (width or 256, height or 256, planes, bits) == (size, size, 1, 32)
        assert ico[offset : offset + length] == (ROOT / f"app/png/kipart-{size}.png").read_bytes()
    icns = (ROOT / "app/kipart-icon.icns").read_bytes()
    assert icns[:4] == b"icns"
    assert struct.unpack_from(">I", icns, 4)[0] == len(icns)
    offset = 8
    slots = {
        b"icp4": 16,
        b"icp5": 32,
        b"icp6": 64,
        b"ic07": 128,
        b"ic08": 256,
        b"ic09": 512,
        b"ic10": 1024,
        b"ic11": 32,
        b"ic12": 64,
        b"ic13": 256,
        b"ic14": 512,
    }
    while offset < len(icns):
        tag, length = struct.unpack_from(">4sI", icns, offset)
        assert (
            icns[offset + 8 : offset + length]
            == (ROOT / f"app/png/kipart-{slots.pop(tag)}.png").read_bytes()
        )
        offset += length
    assert not slots and offset == len(icns)


SCRIPT = """
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QIcon
from kipartmanager.ui.branding import BRANDING_ROOT, application_icon
app = QApplication([])
icon = application_icon()
assert not icon.isNull()
for size in (16,24,32,48,64,128,256,512,1024):
    image = QImage(str(BRANDING_ROOT / f'app/png/kipart-{size}.png'))
    assert not image.isNull() and image.width() == image.height() == size
    assert not icon.pixmap(size,size).isNull()
ico = QIcon(str(BRANDING_ROOT / 'app/kipart-icon.ico'))
assert not ico.isNull() and not ico.pixmap(32,32).isNull()
"""


def test_qt_branding_from_other_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=tmp_path,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
