"""Render the approved SVG unchanged; no external renderer or imaging dependency."""

import struct
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1] / "src/kipartmanager/ui/branding"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def export() -> None:
    """Export PNG-compressed ICO/ICNS containers from the same Qt SVG renderer."""
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(ROOT / "source/app_icon.svg"))
    if not renderer.isValid():
        raise ValueError("Invalid canonical application SVG")
    output = ROOT / "app"
    png = output / "png"
    png.mkdir(parents=True, exist_ok=True)
    images: dict[int, bytes] = {}
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        path = png / f"kipart-{size}.png"
        if not image.save(str(path)):
            raise OSError(f"Cannot export {path}")
        images[size] = path.read_bytes()

    # Windows Vista+ supports PNG payloads, including the 256 px entry (size byte 0).
    sizes = [size for size in SIZES if size <= 256]
    offset = 6 + 16 * len(sizes)
    entries = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    for size in sizes:
        data = images[size]
        entries.extend(
            struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
    (output / "kipart-icon.ico").write_bytes(bytes(entries) + b"".join(images[s] for s in sizes))

    # Modern macOS PNG slots, including Retina 16/32/128/256/512 pt variants.
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
    payload = b"".join(
        tag + struct.pack(">I", len(images[size]) + 8) + images[size] for tag, size in slots.items()
    )
    (output / "kipart-icon.icns").write_bytes(
        b"icns" + struct.pack(">I", len(payload) + 8) + payload
    )
    assert app is not None  # Keep the Qt application alive throughout rendering.


if __name__ == "__main__":
    export()
