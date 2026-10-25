"""Validated convex triangulation and compact, versioned mesh snapshot encoding."""

import math
import struct
from collections.abc import Sequence
from threading import Event
from typing import Any

from kipartmanager.ports.previews import Mesh, PreviewProblem

MAX_TRIANGLES = 60_000


def triangulate(mesh: Mesh, cancel: Event) -> tuple[list[tuple[int, int, int]], list[int]]:
    triangles: list[tuple[int, int, int]] = []
    owners: list[int] = []
    if sum(len(face) ** 2 for face in mesh.faces) > 2_000_000:
        raise PreviewProblem("too_large", "Polygones trop complexes pour l’aperçu.")
    for owner, face in enumerate(mesh.faces):
        if cancel.is_set():
            raise PreviewProblem("cancelled", "Conversion 3D annulée.")
        points = [mesh.vertices[index] for index in face]
        # Newell normal supports polygons whose first three points are collinear.
        normal = [0.0, 0.0, 0.0]
        for a, b in zip(points, points[1:] + points[:1], strict=True):
            normal[0] += (a[1] - b[1]) * (a[2] + b[2])
            normal[1] += (a[2] - b[2]) * (a[0] + b[0])
            normal[2] += (a[0] - b[0]) * (a[1] + b[1])
        extent = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
        length = math.sqrt(sum(v * v for v in normal))
        if extent <= 0 or length <= extent * extent * 1e-10 or len(set(face)) != len(face):
            raise PreviewProblem("error", "Face 3D dégénérée ou indices répétés.")
        normal = [v / length for v in normal]
        if any(
            abs(sum((p[i] - points[0][i]) * normal[i] for i in range(3))) > extent * 1e-6
            for p in points
        ):
            raise PreviewProblem("unsupported", "Polygone 3D non plan non pris en charge.")
        axis = max(range(3), key=lambda i: abs(normal[i]))
        axes = [i for i in range(3) if i != axis]
        flat = [(p[axes[0]] - points[0][axes[0]], p[axes[1]] - points[0][axes[1]]) for p in points]

        def cross(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        area = sum(
            a[0] * b[1] - b[0] * a[1] for a, b in zip(flat, flat[1:] + flat[:1], strict=True)
        )
        sign = 1 if area > 0 else -1
        # Every vertex must lie inside every oriented edge: rejects concavity and stars.
        if any(
            sign * cross(a, b, c) < -extent * extent * 1e-9
            for a, b in zip(flat, flat[1:] + flat[:1], strict=True)
            for c in flat
        ):
            raise PreviewProblem(
                "unsupported", "Face concave ou auto-intersectée non prise en charge."
            )
        for i in range(1, len(face) - 1):
            if abs(cross(flat[0], flat[i], flat[i + 1])) <= extent * extent * 1e-10:
                continue  # Collinear boundary vertex; no surface is removed.
            triangles.append((face[0], face[i], face[i + 1]))
            owners.append(owner)
            if len(triangles) > MAX_TRIANGLES:
                raise PreviewProblem("too_large", "Maillage limité à 60 000 triangles.")
    if not triangles:
        raise PreviewProblem("error", "Aucune surface 3D exploitable.")
    return triangles, owners


def encode_mesh(mesh: Mesh, cancel: Event) -> tuple[bytes, dict[str, Any]]:
    triangles, owners = triangulate(mesh, cancel)
    # FPM1: header u32 vertex/triangle counts; f64 xyz; u32 indices; f32 RGB; u8 sides.
    output = bytearray(struct.pack("<4sII", b"FPM1", len(mesh.vertices), len(triangles)))
    for point in mesh.vertices:
        output.extend(struct.pack("<3d", *point))
    for face in triangles:
        output.extend(struct.pack("<3I", *face))
    for owner in owners:
        output.extend(struct.pack("<3f", *mesh.colors[owner]))
    output.extend(1 if mesh.double_sided and mesh.double_sided[i] else 0 for i in owners)
    bounds = [
        [min(p[i] for p in mesh.vertices) for i in range(3)],
        [max(p[i] for p in mesh.vertices) for i in range(3)],
    ]
    return bytes(output), {
        "mesh_format": "FPM1",
        "vertices": len(mesh.vertices),
        "triangles": len(triangles),
        "bounds": bounds,
        "units": mesh.units,
        "warnings": list(mesh.warnings),
    }
