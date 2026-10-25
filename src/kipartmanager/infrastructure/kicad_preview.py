"""KiCad 6–10 inspection drawings, deliberately separate from qualification.

Coordinates in millimetres; symbol Y points upward, PCB Y downward.
References: dev-docs.kicad.org/en/file-formats/sexpr-intro/ and sexpr-symbol-lib/.
Unsupported graphical constructs are reported, never silently certified.
"""

import math
import re

from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.infrastructure.kicad_parser import Node, check_version, parse
from kipartmanager.ports.previews import Drawing, Primitive

Point = tuple[float, float]


def values(node: Node, tag: str, count: int) -> tuple[float, ...]:
    matches = node.children_named(tag)
    if len(matches) != 1 or len(matches[0].atoms) < count + 1:
        raise DomainError(f"Géométrie incomplète ou ambiguë : {tag}.")
    try:
        result = tuple(float(v) for v in matches[0].atoms[1:])
    except ValueError as error:
        raise DomainError(f"Coordonnée invalide : {tag}.") from error
    if any(not math.isfinite(v) or abs(v) > 100000 for v in result):
        raise DomainError(f"Coordonnée hors limites : {tag}.")
    return result


def point(node: Node, tag: str, symbol: bool) -> Point:
    x, y = values(node, tag, 2)[:2]
    return x, -y if symbol else y


def arc_points(a: Point, b: Point, c: Point) -> tuple[Point, ...]:
    """Sample the circular arc through start, mid and end in that order."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-10:
        raise DomainError("Arc dégénéré : impossible de calculer son aperçu.")
    aa, bb, cc = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    x = (aa * (by - cy) + bb * (cy - ay) + cc * (ay - by)) / d
    y = (aa * (cx - bx) + bb * (ax - cx) + cc * (bx - ax)) / d
    start, mid, end = (math.atan2(py - y, px - x) for px, py in (a, b, c))
    sweep = (end - start) % math.tau
    if (mid - start) % math.tau > sweep:
        sweep -= math.tau
    radius = math.hypot(ax - x, ay - y)
    if not math.isfinite(radius) or radius > 100000:
        raise DomainError("Arc hors limites.")
    return tuple(
        (
            x + radius * math.cos(start + sweep * i / 48),
            y + radius * math.sin(start + sweep * i / 48),
        )
        for i in range(49)
    )


def graphic(node: Node, symbol: bool) -> Primitive:
    tag = node.atoms[0].removeprefix("fp_")
    layer = "Body" if symbol else node.value("layer") or "Other"
    stroke = node.children_named("stroke")
    width = (
        values(stroke[0], "width", 1)[0]
        if stroke
        else (values(node, "width", 1)[0] if node.children_named("width") else 0.15)
    )
    width = max(0.05, width)
    fills = node.children_named("fill")
    filled = bool(
        fills and (fills[0].value("type") in {"background", "outline"} or "yes" in fills[0].atoms)
    )
    if tag in {"line", "rectangle", "rect"}:
        return Primitive(
            "rect" if tag != "line" else "line",
            (point(node, "start", symbol), point(node, "end", symbol)),
            layer,
            width=width,
            filled=filled,
        )
    if tag == "circle":
        centre = point(node, "center", symbol)
        radius = (
            values(node, "radius", 1)[0]
            if symbol
            else math.dist(centre, point(node, "end", symbol))
        )
        if radius <= 0:
            raise DomainError("Rayon de cercle invalide.")
        x, y = centre
        return Primitive(
            "ellipse",
            ((x - radius, y - radius), (x + radius, y + radius)),
            layer,
            width=width,
            filled=filled,
        )
    if tag == "arc":
        return Primitive(
            "line",
            arc_points(
                point(node, "start", symbol), point(node, "mid", symbol), point(node, "end", symbol)
            ),
            layer,
            width=width,
        )
    if tag in {"polyline", "poly"}:
        pts = node.children_named("pts")
        if len(pts) != 1:
            raise DomainError("Polygone sans points.")
        points_list: list[Point] = []
        for pt in pts[0].children_named("xy"):
            if len(pt.atoms) != 3:
                raise DomainError("Point de polygone invalide.")
            x, y = (float(v) for v in pt.atoms[1:])
            if not all(math.isfinite(v) and abs(v) <= 100000 for v in (x, y)):
                raise DomainError("Point de polygone hors limites.")
            points_list.append((x, -y if symbol else y))
        points = tuple(points_list)
        if len(points) < 2:
            raise DomainError("Polygone incomplet.")
        return Primitive(
            "polygon" if filled or tag == "poly" else "line",
            points,
            layer,
            width=width,
            filled=filled,
        )
    raise DomainError("Primitive graphique non prise en charge.")


def hidden(node: Node) -> bool:
    effects = node.children_named("effects")
    return (
        "hide" in node.atoms
        or node.value("hide") == "yes"
        or bool(effects and ("hide" in effects[0].atoms or effects[0].value("hide") == "yes"))
    )


def text_size(node: Node, default: float = 1) -> float:
    effects = node.children_named("effects")
    font = effects[0].children_named("font") if effects else []
    size = values(font[0], "size", 2)[0] if font else default
    if size <= 0:
        raise DomainError("Taille de texte invalide.")
    return size


def pin(node: Node, warnings: set[str], offset: float) -> list[Primitive]:
    x, y, angle = values(node, "at", 3)[:3]
    y = -y
    length = values(node, "length", 1)[0]
    if length < 0:
        raise DomainError("Longueur de broche négative.")
    if hidden(node):
        warnings.add("Broches cachées non affichées.")
        return []
    dx, dy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    end = (x + length * dx, y + length * dy)
    result = [Primitive("line", ((x, y), end), "Pins", width=0.15)]
    for tag, visible, location in (
        (
            "number",
            True,
            (x + length * dx / 2 + dy * 0.45, y + length * dy / 2 - dx * 0.45),
        ),
        ("name", True, (end[0] + dx * (offset + 0.8), end[1] + dy * (offset + 0.8))),
    ):
        child = node.children_named(tag)
        if visible and child and child[0].atoms[1] not in {"", "~"}:
            if "~{" in child[0].atoms[1] or "_{" in child[0].atoms[1] or "^{" in child[0].atoms[1]:
                warnings.add(
                    "Marquage de texte KiCad affiché littéralement (barres, indices, exposants)."
                )
            size = text_size(child[0], 0.9)
            # Neutral DTO texts are centred. Position names inside the body using their
            # estimated glyph extent instead of centring long names over the pin.
            if tag == "name":
                distance = offset + len(child[0].atoms[1]) * size * 0.32
                location = (end[0] + dx * distance, end[1] + dy * distance)
            result.append(
                Primitive(
                    "text",
                    (location,),
                    "Pins",
                    child[0].atoms[1],
                    size=size,
                    angle=-90 if abs(dy) > 0.5 else 0,
                )
            )
    if len(node.atoms) > 2 and node.atoms[2] != "line":
        warnings.add(
            "Décorations électriques des broches simplifiées ; consulter KiCad pour les détails."
        )
    return result


def pad(node: Node, warnings: set[str]) -> list[Primitive]:
    if len(node.atoms) < 4:
        raise DomainError("Pad incomplet.")
    number, shape = node.atoms[1], node.atoms[3]
    layer_nodes = node.children_named("layers")
    if layer_nodes and not {"F.Cu", "*.Cu"}.intersection(layer_nodes[0].atoms[1:]):
        warnings.add(
            f"Pad {number or 'mécanique'} hors cuivre avant non dessiné ; aperçu incomplet."
        )
        return []
    if shape not in {"rect", "roundrect", "circle", "oval"}:
        warnings.add(
            f"Pad {number or 'mécanique'} de forme {shape} non dessiné ; aperçu incomplet."
        )
        return []
    at = values(node, "at", 2)
    x, y = at[:2]
    rotation = -at[2] if len(at) >= 3 else 0
    w, h = values(node, "size", 2)[:2]
    if min(w, h) <= 0:
        raise DomainError("Taille de pad invalide.")
    # Pad shapes are local to their centre; renderer applies the PCB rotation.
    kind = {
        "rect": "pad_rect",
        "roundrect": "pad_round",
        "circle": "pad_ellipse",
        "oval": "pad_oval",
    }[shape]
    radius = 0.25
    if shape == "roundrect":
        radius = values(node, "roundrect_rratio", 1)[0]
        if not 0 <= radius <= 0.5:
            raise DomainError("Rayon de pad arrondi invalide.")
    result = [
        Primitive(
            kind,
            ((x, y), (w, h)),
            "Pad1" if number == "1" else "Pads",
            angle=rotation,
            filled=True,
            size=radius,
        )
    ]
    drills = node.children_named("drill")
    if drills:
        tokens = drills[0].atoms[1:]
        if any(c.atoms[0] == "offset" for c in drills[0].children):
            warnings.add("Perçages décentrés non affichés.")
        elif tokens:
            try:
                dw = float(tokens[1] if tokens[0] == "oval" else tokens[0])
                dh = float(tokens[2]) if tokens[0] == "oval" else dw
                if not all(math.isfinite(v) and 0 < v <= min(w, h) for v in (dw, dh)):
                    raise ValueError
            except (ValueError, IndexError) as error:
                raise DomainError("Perçage invalide.") from error
            result.append(
                Primitive("pad_oval", ((x, y), (dw, dh)), "Drill", angle=rotation, filled=True)
            )
    if number:
        result.append(
            Primitive("text", ((x, y),), "PadLabel", number, size=min(0.9, w * 0.55, h * 0.55))
        )
    return result


def footprint(tree: Node) -> Drawing:
    primitives: list[Primitive] = []
    warnings: set[str] = set()
    for node in tree.children:
        tag = node.atoms[0]
        if tag == "pad":
            primitives.extend(pad(node, warnings))
        elif tag in {"fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly"}:
            primitives.append(graphic(node, False))
        elif tag in {"fp_text", "property"} and not hidden(node):
            if len(node.atoms) < 3:
                raise DomainError("Texte de footprint incomplet.")
            at = values(node, "at", 2)
            primitives.append(
                Primitive(
                    "annotation",
                    (point(node, "at", False),),
                    node.value("layer"),
                    node.atoms[2],
                    angle=-at[2] if len(at) > 2 else 0,
                    size=text_size(node),
                )
            )
        elif tag.startswith("fp_") or tag in {"zone", "image"}:
            warnings.add(f"Élément {tag} non affiché ; aperçu incomplet.")
    return Drawing(tree.atoms[1], 1, 1, tuple(primitives), tuple(sorted(warnings)))


def symbols(
    tree: Node, selected: str, max_drawings: int = 2048, max_primitives: int = 100000
) -> tuple[Drawing, ...]:
    entries: dict[str, Node] = {}
    for node in tree.children_named("symbol"):
        if len(node.atoms) != 2 or node.atoms[1] in entries:
            raise DomainError("Identité de symbole absente ou dupliquée.")
        entries[node.atoms[1]] = node
    if selected and selected not in entries:
        raise DomainError("Symbole sélectionné absent du fichier.")
    result: list[Drawing] = []
    total = 0
    geometry_cost = 0
    for name in [selected] if selected else entries:
        chain: list[Node] = []
        current = name
        seen: set[str] = set()
        while current:
            if current in seen or current not in entries or len(seen) >= 64:
                raise DomainError("Héritage absent, cyclique ou trop profond.")
            seen.add(current)
            chain.insert(0, entries[current])
            current = entries[current].value("extends")
        units: list[tuple[int, int, Node]] = []
        for entry in chain:
            for unit in entry.children_named("symbol"):
                match = re.fullmatch(re.escape(entry.atoms[1]) + r"_(\d+)_(\d+)", unit.atoms[1])
                if not match:
                    raise DomainError("Identifiant d’unité non reconnu.")
                units.append((int(match[1]), int(match[2]), unit))
        unit_ids = sorted({u for u, _, _ in units if u}) or [1]
        styles = sorted({s for _, s, _ in units if s}) or [1]
        if len(unit_ids) * len(styles) + len(result) > max_drawings:
            raise DomainError("Trop d’unités ou de représentations pour cet aperçu.")
        for unit_id in unit_ids:
            for style in styles:
                primitives: list[Primitive] = []
                warnings: set[str] = set()
                offset = 0.508
                for entry in chain:
                    for child in entry.children_named("pin_names"):
                        if child.children_named("offset"):
                            offset = values(child, "offset", 1)[0]
                for u, s, node in units:
                    if u not in {0, unit_id} or s not in {0, style}:
                        continue
                    for child in node.children:
                        tag = child.atoms[0]
                        if tag == "pin":
                            primitives.extend(pin(child, warnings, offset))
                        elif tag in {"rectangle", "circle", "polyline", "arc"}:
                            primitives.append(graphic(child, True))
                        elif tag == "text" and not hidden(child):
                            at = values(child, "at", 3)
                            primitives.append(
                                Primitive(
                                    "text",
                                    (point(child, "at", True),),
                                    text=child.atoms[1],
                                    angle=-at[2] / 10,
                                    size=text_size(child),
                                )
                            )
                        else:
                            warnings.add(f"Élément {tag} non affiché ; aperçu incomplet.")
                geometry_cost += sum(len(p.points) + len(p.text) for p in primitives)
                if geometry_cost > max_primitives * 20:
                    raise DomainError("Géométrie ou textes trop complexes pour cet aperçu.")
                total += len(primitives)
                if total > max_primitives:
                    raise DomainError("Trop d’éléments graphiques pour cet aperçu.")
                result.append(
                    Drawing(name, unit_id, style, tuple(primitives), tuple(sorted(warnings)))
                )
                if len(result) > max_drawings:
                    raise DomainError(
                        "Bibliothèque trop grande pour l’aperçu ; sélectionner un symbole."
                    )
    return tuple(result)


def drawings(
    text: str,
    kind: AssetType,
    selected: str = "",
    *,
    max_drawings: int = 2048,
    max_primitives: int = 100000,
) -> tuple[Drawing, ...]:
    try:
        tree = parse(text)
        check_version(tree, kind is AssetType.SYMBOL)
        result = (
            symbols(tree, selected, max_drawings, max_primitives)
            if kind is AssetType.SYMBOL
            else (footprint(tree),)
        )
        if not result:
            raise DomainError("Aucun symbole à afficher.")
        if sum(len(d.primitives) for d in result) > max_primitives:
            raise DomainError("Trop d’éléments graphiques pour cet aperçu.")
        return result
    except DomainError:
        raise
    except (IndexError, ValueError, OverflowError) as error:
        raise DomainError("Géométrie KiCad incomplète ou invalide.") from error
