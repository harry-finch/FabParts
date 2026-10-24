"""Bounded VRML97 subset and optional isolated local FreeCAD STEP tessellation."""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kipartmanager.domain.entities import DomainError
from kipartmanager.ports.previews import Mesh

MAX_VERTICES = 60_000
MAX_FACES = 20_000
MAX_OUTPUT = 16 * 1024 * 1024
NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\Z")
TOKEN = re.compile(r'\s+|\#[^\n]*|"(?:[^"\\]|\\.)*"|[{}\[\],]|[^\s{}\[\],#]+')
VECTOR_FIELDS = {
    "translation": 3,
    "scale": 3,
    "center": 3,
    "rotation": 4,
    "scaleOrientation": 4,
    "diffuseColor": 3,
    "specularColor": 3,
    "emissiveColor": 3,
    "bboxCenter": 3,
    "bboxSize": 3,
    "size": 3,
}
Matrix = tuple[tuple[float, ...], ...]
IDENTITY: Matrix = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


@dataclass
class Node:
    kind: str
    fields: dict[str, object]


class VRML:
    def __init__(self, text: str) -> None:
        self.tokens = []
        for match in TOKEN.finditer(text):
            token = match.group()
            if not token.isspace() and not token.startswith("#") and token != ",":
                self.tokens.append(token)
            if len(self.tokens) > 600_000:
                raise DomainError("WRL trop complexe pour l’aperçu.")
        self.index = 0
        self.definitions: dict[str, Node] = {}

    def pop(self) -> str:
        if self.index >= len(self.tokens):
            raise DomainError("WRL tronqué.")
        value = self.tokens[self.index]
        self.index += 1
        return value

    def expect(self, value: str) -> None:
        if self.pop() != value:
            raise DomainError("Structure WRL non reconnue.")

    def value(self, depth: int = 0) -> object:
        if depth > 48:
            raise DomainError("WRL trop imbriqué.")
        token = self.pop()
        if token == "[":
            items = []
            while self.index < len(self.tokens) and self.tokens[self.index] != "]":
                items.append(self.value(depth + 1))
            self.expect("]")
            return items
        if NUMBER.fullmatch(token):
            number = float(token)
            if not math.isfinite(number) or abs(number) > 1e9:
                raise DomainError("Coordonnée WRL hors limites.")
            return number
        if token == "USE":
            name = self.pop()
            if name not in self.definitions:
                raise DomainError("Référence USE WRL inconnue ou cyclique.")
            return self.definitions[name]
        if token == "DEF":
            name = self.pop()
            node = self.value(depth + 1)
            if not isinstance(node, Node):
                raise DomainError("Définition WRL invalide.")
            self.definitions[name] = node
            return node
        if token.startswith('"') or token in {"TRUE", "FALSE", "NULL"}:
            return token
        if token in {"Inline", "Script", "PROTO", "EXTERNPROTO", "ROUTE"}:
            raise DomainError(
                "WRL externe, scripté ou dynamique non pris en charge ; aucun accès externe."
            )
        self.expect("{")
        fields: dict[str, object] = {}
        while self.index < len(self.tokens) and self.tokens[self.index] != "}":
            key = self.pop()
            if key in fields:
                raise DomainError("Champ WRL dupliqué.")
            fields[key] = (
                [self.value(depth + 1) for _ in range(VECTOR_FIELDS[key])]
                if key in VECTOR_FIELDS
                else self.value(depth + 1)
            )
        self.expect("}")
        return Node(token, fields)


def numbers(value: object, length: int | None = None) -> list[float]:
    if not isinstance(value, list) or any(
        type(v) is not float or not math.isfinite(v) or abs(v) > 1e9 for v in value
    ):
        raise DomainError("Liste numérique 3D invalide.")
    if length is not None and len(value) != length:
        raise DomainError("Dimensions 3D invalides.")
    return [float(v) for v in value]


def multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)) for i in range(4)
    )


def translate(values: list[float]) -> Matrix:
    return tuple(
        tuple(values[i] if j == 3 and i < 3 else IDENTITY[i][j] for j in range(4)) for i in range(4)
    )


def rotate(values: list[float]) -> Matrix:
    x, y, z, angle = values
    length = math.sqrt(x * x + y * y + z * z)
    if length == 0:
        if angle != 0:
            raise DomainError("Axe de rotation WRL nul.")
        return IDENTITY
    x, y, z = x / length, y / length, z / length
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0.0),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0.0),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def transform(node: Node) -> Matrix:
    f = node.fields
    center = numbers(f.get("center", [0.0, 0.0, 0.0]), 3)
    orientation = numbers(f.get("scaleOrientation", [0.0, 0.0, 1.0, 0.0]), 4)
    scale = numbers(f.get("scale", [1.0, 1.0, 1.0]), 3)
    if any(v <= 0 for v in scale):
        raise DomainError("Échelle WRL nulle ou négative non prise en charge.")
    matrix = translate(numbers(f.get("translation", [0.0, 0.0, 0.0]), 3))
    for part in (
        translate(center),
        rotate(numbers(f.get("rotation", [0.0, 0.0, 1.0, 0.0]), 4)),
        rotate(orientation),
        tuple(
            tuple(scale[i] if i == j and i < 3 else IDENTITY[i][j] for j in range(4))
            for i in range(4)
        ),
        rotate(orientation[:3] + [-orientation[3]]),
        translate([-v for v in center]),
    ):
        matrix = multiply(matrix, part)
    return matrix


def checked_mesh(
    vertices: object, faces: object, colors: object, warnings: tuple[str, ...] = ()
) -> Mesh:
    if not isinstance(vertices, list) or not 0 < len(vertices) <= MAX_VERTICES:
        raise DomainError("Nombre de sommets 3D hors limites.")
    points = tuple(tuple(numbers(v, 3)) for v in vertices)
    if not isinstance(faces, list) or not 0 < len(faces) <= MAX_FACES:
        raise DomainError("Nombre de faces 3D hors limites.")
    polygons = []
    for face in faces:
        if (
            not isinstance(face, list)
            or not 3 <= len(face) <= 256
            or any(type(i) is not int or not 0 <= i < len(points) for i in face)
        ):
            raise DomainError("Indices de faces 3D invalides.")
        polygons.append(tuple(face))
    if not isinstance(colors, list) or len(colors) != len(polygons):
        raise DomainError("Couleurs de faces 3D invalides.")
    shades = []
    for color in colors:
        rgb = numbers(color, 3)
        if any(not 0 <= v <= 1 for v in rgb):
            raise DomainError("Couleur 3D hors limites.")
        shades.append(tuple(rgb))
    # Tuple arity is checked above, then made explicit for the presentation port.
    return Mesh(
        tuple((p[0], p[1], p[2]) for p in points),
        tuple(polygons),
        tuple((c[0], c[1], c[2]) for c in shades),
        warnings,
    )


def wrl_mesh(content: bytes) -> Mesh:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError as error:
        raise DomainError("WRL non UTF-8.") from error
    if not text.startswith("#VRML V2.0 utf8"):
        raise DomainError("Seul le WRL VRML97 (#VRML V2.0 utf8) est pris en charge.")
    parser = VRML(text)
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    colors: list[list[float]] = []
    warnings: set[str] = set()

    def visit(value: object, matrix: Matrix = IDENTITY, depth: int = 0) -> None:
        if depth > 48:
            raise DomainError("Scène WRL trop imbriquée.")
        if isinstance(value, list):
            for child in value:
                visit(child, matrix, depth + 1)
        elif isinstance(value, Node):
            f = value.fields
            if value.kind in {"Transform", "Group"}:
                local = multiply(matrix, transform(value)) if value.kind == "Transform" else matrix
                visit(f.get("children", []), local, depth + 1)
            elif value.kind == "Shape":
                geom = f.get("geometry")
                if not isinstance(geom, Node) or geom.kind != "IndexedFaceSet":
                    raise DomainError("Géométrie WRL non prise en charge : IndexedFaceSet requis.")
                if geom.fields.get("convex") == "FALSE":
                    raise DomainError("Faces WRL déclarées non convexes non prises en charge.")
                coord = geom.fields.get("coord")
                if not isinstance(coord, Node) or coord.kind != "Coordinate":
                    raise DomainError("Sommets WRL manquants.")
                points = numbers(coord.fields.get("point"))
                if len(points) % 3 or len(vertices) + len(points) // 3 > MAX_VERTICES:
                    raise DomainError("Sommets WRL invalides ou trop nombreux.")
                base = len(vertices)
                for i in range(0, len(points), 3):
                    p = points[i : i + 3] + [1.0]
                    vertices.append([sum(matrix[j][k] * p[k] for k in range(4)) for j in range(3)])
                color = [0.65, 0.68, 0.72]
                appearance = f.get("appearance")
                if isinstance(appearance, Node):
                    material = appearance.fields.get("material")
                    if isinstance(material, Node):
                        color = numbers(material.fields.get("diffuseColor", color), 3)
                        if material.fields.get("transparency", 0.0) != 0.0:
                            warnings.add("Transparence simplifiée en surface opaque.")
                    if "texture" in appearance.fields:
                        warnings.add("Textures ignorées ; aucun fichier externe chargé.")
                if "color" in geom.fields:
                    warnings.add("Couleurs par sommet/face ignorées ; matériau diffus conservé.")
                indices = numbers(geom.fields.get("coordIndex"))
                face: list[int] = []
                for index in indices:
                    if index == -1:
                        if len(face) < 3:
                            raise DomainError("Face WRL incomplète.")
                        faces.append(face)
                        colors.append(color)
                        face = []
                        if len(faces) > MAX_FACES:
                            raise DomainError("Trop de faces pour l’aperçu interactif.")
                    elif index != int(index) or not 0 <= index < len(points) // 3:
                        raise DomainError("Indice WRL hors limites.")
                    else:
                        face.append(base + int(index))
                        if len(face) > 256:
                            raise DomainError("Face WRL trop complexe.")
                if face:
                    faces.append(face)
                    colors.append(color)
            elif value.kind not in {
                "Appearance",
                "Material",
                "Coordinate",
                "Normal",
                "Color",
                "TextureCoordinate",
                "IndexedFaceSet",
                "WorldInfo",
                "NavigationInfo",
                "Viewpoint",
                "Background",
                "DirectionalLight",
                "PointLight",
                "SpotLight",
            }:
                raise DomainError(f"Nœud WRL non pris en charge : {value.kind}.")

    while parser.index < len(parser.tokens):
        visit(parser.value())
    return checked_mesh(vertices, faces, colors, tuple(sorted(warnings)))


# Executed by FreeCAD's own Python, never by the application's interpreter.
STEP_SCRIPT = """import json, os
import Part
shape = Part.Shape()
shape.read(os.environ['KIPART_PREVIEW_INPUT'])
if shape.isNull():
    raise ValueError('Empty STEP shape')
vertices, faces = shape.tessellate(0.15)
if len(vertices) > 60000 or len(faces) > 20000:
    raise ValueError('Mesh limit exceeded')
with open(os.environ['KIPART_PREVIEW_OUTPUT'], 'w') as stream:
    json.dump({'vertices': [[float(v.x), float(v.y), float(v.z)] for v in vertices],
               'faces': [list(f) for f in faces]}, stream)
"""


def freecad_command() -> str | None:
    configured = os.environ.get("KIPART_FREECAD_CMD")
    if configured:
        return configured if Path(configured).is_file() else None
    for name in ("freecadcmd", "FreeCADCmd"):
        command = shutil.which(name)
        if command:
            return command
    if sys.platform == "darwin":
        for folder in (Path("/Applications"), Path.home() / "Applications"):
            path = folder / "FreeCAD.app/Contents/Resources/bin/freecadcmd"
            if path.is_file():
                return str(path)
    return None


def step_mesh(content: bytes) -> Mesh:
    if not content.lstrip().startswith(b"ISO-10303-21;"):
        raise DomainError("En-tête STEP non reconnu.")
    command = freecad_command()
    if command is None:
        raise DomainError(
            "Aperçu STEP indisponible : installer FreeCAD local ou définir "
            "KIPART_FREECAD_CMD vers freecadcmd. Aucun téléchargement automatique."
        )
    with tempfile.TemporaryDirectory(prefix="kipart-preview-") as directory:
        root = Path(directory)
        source, target, script = root / "snapshot.step", root / "mesh.json", root / "preview.py"
        source.write_bytes(content)
        script.write_text(STEP_SCRIPT, encoding="utf-8")
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith(("QT_", "PYTHON"))
        }
        environment.update(
            KIPART_PREVIEW_INPUT=str(source),
            KIPART_PREVIEW_OUTPUT=str(target),
            QT_QPA_PLATFORM="offscreen",
            XDG_CONFIG_HOME=str(root),
        )
        try:
            # Logs go to a disposable file; no unbounded PIPE buffer in application memory.
            with (root / "freecad.log").open("wb") as log:
                result = subprocess.run(
                    [
                        command,
                        "-u",
                        str(root / "user.cfg"),
                        "-s",
                        str(root / "system.cfg"),
                        str(script),
                    ],
                    cwd=root,
                    env=environment,
                    stdout=log,
                    stderr=log,
                    timeout=30,
                    check=False,
                )
            if result.returncode != 0 or not target.is_file():
                raise DomainError(
                    "FreeCAD n’a pas pu lire ce STEP ou le maillage dépasse les limites."
                )
            with target.open("rb") as stream:
                data = stream.read(MAX_OUTPUT + 1)
            if len(data) > MAX_OUTPUT:
                raise DomainError("Maillage STEP trop volumineux pour l’aperçu.")
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError("mesh")
            faces = payload.get("faces")
            count = len(faces) if isinstance(faces, list) else 0
            mesh = checked_mesh(
                payload.get("vertices"),
                faces,
                [[0.65, 0.68, 0.72]] * count,
                (
                    "STEP tessellé à 0,15 mm ; matériaux simplifiés. "
                    "L’aperçu ne constitue pas une mesure ni une validation.",
                ),
            )
            return mesh
        except subprocess.TimeoutExpired as error:
            raise DomainError("Conversion STEP interrompue après 30 secondes.") from error
        except (OSError, ValueError, RecursionError) as error:
            raise DomainError("Moteur STEP indisponible ou maillage illisible.") from error


def model_mesh(content: bytes) -> Mesh:
    return wrl_mesh(content) if content.lstrip().startswith(b"#VRML") else step_mesh(content)
