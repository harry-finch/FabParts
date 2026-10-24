"""Small software mesh viewer: orthographic inspection, no GPU or CAD dependency."""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from kipartmanager.application.previews import Mesh
from kipartmanager.ui.theme import PREVIEW_COLORS


class ModelView(QWidget):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.mesh: Mesh | None = None
        self.image = QImage()
        self.image_key: tuple[object, ...] = ()
        self.yaw, self.pitch = -35.0, 55.0
        self.magnification = 1.0
        self.interacting = False
        self.pan = QPointF()
        self.last = QPointF()
        self.setMinimumSize(240, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Aperçu 3D en lecture seule")
        self.setToolTip(
            "Glisser : rotation ; glisser avec le bouton droit : déplacement ; "
            "molette : zoom ; Recentrer : cadrage initial."
        )
        self.points: tuple[tuple[float, float, float], ...] = ()

    def display(self, mesh: Mesh) -> None:
        self.mesh = mesh
        bounds = [
            (min(p[i] for p in mesh.vertices), max(p[i] for p in mesh.vertices)) for i in range(3)
        ]
        center = [(a + b) / 2 for a, b in bounds]
        radius = (
            max(math.sqrt(sum((p[i] - center[i]) ** 2 for i in range(3))) for p in mesh.vertices)
            or 1.0
        )
        self.points = tuple(
            ((p[0] - center[0]) / radius, (p[1] - center[1]) / radius, (p[2] - center[2]) / radius)
            for p in mesh.vertices
        )
        self.fit()

    def fit(self) -> None:
        self.magnification, self.pan = 1.0, QPointF()
        self.update()

    def standard_view(self, index: int) -> None:
        self.yaw, self.pitch = [(-35.0, 55.0), (0.0, 0.0), (0.0, 90.0), (90.0, 90.0)][index]
        self.fit()

    def zoom(self, factor: float) -> None:
        self.magnification = min(15.0, max(0.15, self.magnification * factor))
        self.update()

    def project(self, p: tuple[float, ...]) -> tuple[float, float, float]:
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        x = math.cos(yaw) * p[0] - math.sin(yaw) * p[1]
        y = math.sin(yaw) * p[0] + math.cos(yaw) * p[1]
        return (
            x,
            math.cos(pitch) * y - math.sin(pitch) * p[2],
            math.sin(pitch) * y + math.cos(pitch) * p[2],
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PREVIEW_COLORS["Background"]))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        mesh = self.mesh
        if mesh is None:
            return
        key = (
            id(mesh),
            self.width(),
            self.height(),
            self.yaw,
            self.pitch,
            self.magnification,
            self.pan.x(),
            self.pan.y(),
            self.interacting,
        )
        if key != self.image_key:
            self.image = self.raster(mesh)
            self.image_key = key
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self.image)
        painter.setPen(QColor(PREVIEW_COLORS["Body"]))
        painter.drawText(12, 22, "3D · projection orthographique")
        origin = QPointF(40, self.height() - 38)
        for axis, name in [((1.0, 0.0, 0.0), "X"), ((0.0, 1.0, 0.0), "Y"), ((0.0, 0.0, 1.0), "Z")]:
            x, y, _ = self.project(axis)
            end = origin + QPointF(x * 24, -y * 24)
            painter.drawLine(origin, end)
            painter.drawText(end + QPointF(3, -3), name)

    def raster(self, mesh: Mesh) -> QImage:
        # A small cached depth buffer gives correct occlusion without a GPU requirement.
        ratio = min(
            self.devicePixelRatioF(),
            (480 if self.interacting else 1280) / max(self.width(), self.height()),
        )
        width, height = max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio))
        background = QColor(PREVIEW_COLORS["Background"])
        pixels = bytearray(
            bytes((background.blue(), background.green(), background.red(), 255)) * width * height
        )
        depths = [-math.inf] * (width * height)
        scale = min(width, height) * 0.42 * self.magnification
        cx, cy = width / 2 + self.pan.x() * ratio, height / 2 + self.pan.y() * ratio
        points = [(cx + x * scale, cy - y * scale, z) for x, y, z in map(self.project, self.points)]
        for face, rgb in zip(mesh.faces, mesh.colors, strict=True):
            a, b, c = (points[v] for v in face[:3])
            u, v = [b[j] - a[j] for j in range(3)], [c[j] - a[j] for j in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            # Screen coordinates scale x/y but not z; restore them for lighting.
            normal = (n[0] * scale, n[1] * scale, n[2])
            length = math.sqrt(sum(k * k for k in normal))
            light = 0.45 + 0.55 * abs(normal[2] / length) if length else 0.65
            color = bytes(
                (
                    round(rgb[2] * light * 255),
                    round(rgb[1] * light * 255),
                    round(rgb[0] * light * 255),
                    255,
                )
            )
            for i in range(1, len(face) - 1):
                triangle = [points[face[0]], points[face[i]], points[face[i + 1]]]
                low = max(0, math.ceil(min(p[1] for p in triangle) - 0.5))
                high = min(height - 1, math.floor(max(p[1] for p in triangle) - 0.5))
                for row in range(low, high + 1):
                    y = row + 0.5
                    hits = []
                    for p, q in zip(triangle, triangle[1:] + triangle[:1], strict=True):
                        if min(p[1], q[1]) <= y < max(p[1], q[1]):
                            t = (y - p[1]) / (q[1] - p[1])
                            hits.append((p[0] + t * (q[0] - p[0]), p[2] + t * (q[2] - p[2])))
                    if len(hits) != 2:
                        continue
                    (left, zleft), (right, zright) = sorted(hits)
                    if right - left < 1e-12:
                        continue
                    first = max(0, math.ceil(left - 0.5))
                    last = min(width - 1, math.floor(right - 0.5))
                    dz = (zright - zleft) / (right - left)
                    z = zleft + (first + 0.5 - left) * dz
                    offset = row * width + first
                    for _ in range(first, last + 1):
                        if z > depths[offset]:
                            depths[offset] = z
                            pos = offset * 4
                            pixels[pos : pos + 4] = color
                        offset += 1
                        z += dz
        return QImage(pixels, width, height, width * 4, QImage.Format.Format_ARGB32).copy()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.last = event.position()
            self.interacting = True
            self.setFocus()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        delta = event.position() - self.last
        if event.buttons() & Qt.MouseButton.RightButton:
            self.pan += delta
        elif event.buttons() & Qt.MouseButton.LeftButton:
            self.yaw += delta.x() * 0.5
            self.pitch += delta.y() * 0.5
        else:
            super().mouseMoveEvent(event)
            return
        self.last = event.position()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.interacting = False
        self.update()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y():
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()
