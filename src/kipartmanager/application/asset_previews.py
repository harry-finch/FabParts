"""Read-only business resolution and bounded neutral previews for the desktop IPC."""

import math
from dataclasses import asdict
from typing import Any
from uuid import UUID

from kipartmanager.application.catalogue_reader import CatalogueReader
from kipartmanager.application.model_jobs import ModelJobs
from kipartmanager.application.preview_buffers import PreviewBuffers
from kipartmanager.application.previews import Previews
from kipartmanager.domain.entities import Asset, AssetType, DomainError, Package, Part
from kipartmanager.domain.resolution import ResourceChoice
from kipartmanager.ports.previews import (
    PDF_CHUNK,
    PDF_LIMIT,
    Drawing,
    PreviewContent,
    PreviewProblem,
    PreviewReader,
    Primitive,
)


def bounds(primitives: tuple[Primitive, ...]) -> list[float]:
    """Conservative mm bounds including text and rotated pads, never package-name guesses."""
    points: list[tuple[float, float]] = []
    for p in primitives:
        x, y = p.points[0]
        if p.kind.startswith("pad_"):
            w, h = p.points[1]
        elif p.kind in {"text", "annotation"}:
            w, h = max(1, len(p.text)) * p.size, 1.5 * p.size
        else:
            points.extend((a - p.width, b - p.width) for a, b in p.points)
            points.extend((a + p.width, b + p.width) for a, b in p.points)
            continue
        angle = math.radians(p.angle)
        for a, b in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
            points.append(
                (
                    x + a * math.cos(angle) - b * math.sin(angle),
                    y + a * math.sin(angle) + b * math.cos(angle),
                )
            )
    if not points:
        return [-1, -1, 2, 2]
    xs, ys = zip(*points, strict=True)
    x, y = min(xs), min(ys)
    w, h = max(xs) - x, max(ys) - y
    margin = max(w, h, 1) * 0.06
    return [x - margin, y - margin, max(w, 0.1) + 2 * margin, max(h, 0.1) + 2 * margin]


def drawing_dto(drawing: Drawing) -> dict[str, Any]:
    result = asdict(drawing)
    result.update(bounds=bounds(drawing.primitives), units="mm")
    return result


class AssetPreviews:
    def __init__(
        self, catalogue: CatalogueReader, reader: PreviewReader, models: ModelJobs | None = None
    ) -> None:
        self.catalogue = catalogue
        self.previews = Previews(catalogue.catalogue, reader)
        self.buffers = PreviewBuffers()
        self.handles = self.buffers.handles
        self.models = models

    def _expire(self) -> None:
        self.buffers.expire()

    def clear(self) -> None:
        self.handles.clear()
        if self.models:
            self.models.close()

    def resolve(
        self, identity: UUID, role: AssetType, asset_id: UUID | None
    ) -> tuple[ResourceChoice, bool]:
        cat = self.catalogue
        part = cat.catalogue.require(Part, identity)
        owner: Part | Package = part
        if role in {AssetType.FOOTPRINT, AssetType.MODEL_3D}:
            if not part.package_id:
                raise PreviewProblem("absent", "Aucun boîtier associé.")
            owner = cat.catalogue.require(Package, part.package_id)
        choices = cat.repository.choices(owner)
        selected = next((c for c in choices if c.asset_type == role), None)
        if asset_id is None:
            if selected:
                return selected, True
            raise PreviewProblem(
                "absent",
                "Aucune ressource sélectionnée. Choisissez un aperçu associé si disponible.",
            )
        allowed = set(owner.asset_ids)
        if role is AssetType.DATASHEET:
            allowed.update(d.asset_id for d in cat.documentation.documents(part.id))
        if asset_id not in allowed:
            raise PreviewProblem("inaccessible", "Cette ressource n’est pas associée au composant.")
        asset = cat.catalogue.require(Asset, asset_id)
        if asset.asset_type != role:
            raise PreviewProblem("unsupported", "Le type ne correspond pas au rôle demandé.")
        return ResourceChoice(role, asset_id=asset_id), bool(
            selected and selected.asset_id == asset_id
        )

    def get(self, id: str, role: str, asset_id: str = "") -> dict[str, Any]:
        self._expire()
        try:
            kind = AssetType(role)
            if kind is AssetType.MODEL_3D and self.models is None:
                raise PreviewProblem("unsupported", "Service 3D indisponible.")
            choice, selected = self.resolve(UUID(id), kind, UUID(asset_id) if asset_id else None)
            if (
                choice.asset_id
                and self.catalogue.catalogue.require(Asset, choice.asset_id).file is None
            ):
                raise PreviewProblem("absent", "Aucun fichier associé à cette ressource.")
            preview = self.previews.inspect(choice)
            result: dict[str, Any] = {
                "status": "ready",
                "kind": kind.value,
                "selected": selected,
                "name": choice.reference.identifier if choice.reference else preview.name,
                "origin": preview.origin,
                "source": preview.source,
                "sha256": preview.sha256,
                "storage": "reference" if choice.reference else "managed",
            }
            return self.present(kind, preview.content, result)
        except PreviewProblem as error:
            return {"status": error.status, "message": str(error)}
        except DomainError as error:
            return {"status": "error", "message": str(error)}

    def present(
        self, kind: AssetType, content: PreviewContent, result: dict[str, Any]
    ) -> dict[str, Any]:
        """Shared bounded transport for canonical and preparation previews."""
        if kind is AssetType.MODEL_3D:
            if self.models is None:
                raise PreviewProblem("unsupported", "Service 3D indisponible.")
            result.update(status="loading", handle=self.models.start(content.model_source))
        elif kind is AssetType.DATASHEET:
            data = content.pdf
            if len(data) > PDF_LIMIT:
                raise PreviewProblem("too_large", "PDF limité à 16 Mio.")
            handle = self.buffers.put(data)
            result.update(handle=handle, size_bytes=len(data), chunk_bytes=PDF_CHUNK)
        else:
            drawings = content.drawings
            if len(drawings) > 64 or sum(len(d.primitives) for d in drawings) > 5000:
                raise PreviewProblem(
                    "too_large", "Aperçu limité à 64 représentations et 5 000 primitives."
                )
            result["drawings"] = [drawing_dto(d) for d in drawings]
        return result

    def chunk(self, handle: str, offset: int) -> dict[str, Any]:
        return self.buffers.chunk(handle, offset)

    def release(self, handle: str) -> dict[str, bool]:
        self.buffers.release(handle)
        return {"released": True}
