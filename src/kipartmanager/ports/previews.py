"""Read-only preview snapshots and presentation-neutral drawing primitives."""

from dataclasses import dataclass
from typing import Protocol

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.kicad import KiCadReference


@dataclass(frozen=True)
class Primitive:
    kind: str
    points: tuple[tuple[float, float], ...]
    layer: str = "Body"
    text: str = ""
    width: float = 0.15
    filled: bool = False
    angle: float = 0
    size: float = 1


@dataclass(frozen=True)
class Drawing:
    name: str
    unit: int
    style: int
    primitives: tuple[Primitive, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mesh:
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]
    colors: tuple[tuple[float, float, float], ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviewContent:
    drawings: tuple[Drawing, ...] = ()
    pdf: bytes = b""
    mesh: Mesh | None = None


class PreviewReader(Protocol):
    def managed(self, file: AssetFile) -> PreviewContent: ...

    def official(self, reference: KiCadReference) -> PreviewContent: ...
