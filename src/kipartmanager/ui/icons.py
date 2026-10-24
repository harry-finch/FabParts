"""Local Lucide SVGs, pinned and licensed; no runtime download or dependency."""

from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPainter


def icon(name: str, *, color: str | None = None) -> QIcon:
    source = QIcon(str(Path(__file__).parent / "icons" / f"{name}.svg"))
    if color is None:
        return source
    tinted = QIcon()
    for size in (16, 24, 32, 48, 64):
        pixmap = source.pixmap(size, size)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        tinted.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.Off)
    return tinted
