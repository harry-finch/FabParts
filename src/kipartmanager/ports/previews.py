"""Read-only preview snapshots and presentation-neutral drawing primitives."""

from dataclasses import dataclass
from typing import Protocol

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import DomainError
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


PDF_LIMIT = 16 * 1024 * 1024
PDF_CHUNK = 64 * 1024
HANDLE_TTL = 120
MAX_HANDLES = 2


class PreviewProblem(DomainError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
