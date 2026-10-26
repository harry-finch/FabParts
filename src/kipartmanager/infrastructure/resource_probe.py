"""Read-only bounded format inspection; full CAO/PDF validation is excluded."""

import math
from pathlib import Path

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.domain.validation import Inspection
from kipartmanager.infrastructure.asset_store import LocalAssetStore
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_parser import Node, check_version, parse


def descendants(root: Node, tag: str) -> list[Node]:
    result = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.atoms[0] == tag:
            result.append(node)
        stack.extend(reversed(node.children))
    return result


def numbers(node: Node, tag: str, minimum: int, positive: bool = False) -> None:
    children = node.children_named(tag)
    if len(children) != 1 or len(children[0].atoms) < minimum + 1:
        raise DomainError(f"Champ {tag} absent, incomplet ou dupliqué.")
    try:
        values = [float(value) for value in children[0].atoms[1:]]
    except ValueError as error:
        raise DomainError(f"Champ {tag} non numérique.") from error
    if any(not math.isfinite(value) or (positive and value <= 0) for value in values):
        raise DomainError(f"Champ {tag} invalide.")


def symbol_info(tree: Node, selected: str) -> tuple[str, tuple[str, ...], str]:
    check_version(tree, True)
    symbols = tree.children_named("symbol")
    entries: dict[str, Node] = {}
    for node in symbols:
        if len(node.atoms) != 2 or node.atoms[1] in entries:
            raise DomainError("Nom de symbole absent ou dupliqué.")
        entries[node.atoms[1]] = node
    if not selected:
        if len(entries) != 1:
            raise DomainError("Bibliothèque gérée multi-symboles ou vide : entrée non déterminée.")
        selected = next(iter(entries))
    nodes: list[Node] = []
    seen: set[str] = set()
    name = selected
    while name:
        if name in seen or name not in entries or len(seen) >= 64:
            raise DomainError("Héritage de symbole absent, cyclique ou trop profond.")
        seen.add(name)
        node = entries[name]
        nodes.append(node)
        name = node.value("extends")
    pins: set[str] = set()
    properties: dict[str, str] = {}
    for node in reversed(nodes):
        for prop in node.children_named("property"):
            if len(prop.atoms) < 3:
                raise DomainError("Propriété de symbole incomplète.")
            properties[prop.atoms[1]] = prop.atoms[2]
        for pin in descendants(node, "pin"):
            number = pin.value("number")
            if len(pin.atoms) != 3 or not number:
                raise DomainError("Pin sans numéro ou définition incomplète.")
            numbers(pin, "at", 3)
            numbers(pin, "length", 1)
            if float(pin.value("length")) < 0:
                raise DomainError("Longueur de pin négative.")
            pins.add(number)
    if not pins:
        raise DomainError("Symbole sans pins électriques.")
    return selected, tuple(sorted(pins)), properties.get("Footprint", "")


def footprint_info(tree: Node) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    check_version(tree, False)
    if len(tree.atoms) != 2:
        raise DomainError("Nom de footprint absent ou ambigu.")
    pads: set[str] = set()
    for pad in tree.children_named("pad"):
        if len(pad.atoms) != 4 or pad.atoms[2] not in {
            "smd",
            "thru_hole",
            "np_thru_hole",
            "connect",
        }:
            raise DomainError("Type de pad absent ou non supporté.")
        numbers(pad, "at", 2)
        numbers(pad, "size", 2, True)
        layers = pad.children_named("layers")
        if len(layers) != 1 or len(layers[0].atoms) < 2:
            raise DomainError("Pad sans couches.")
        if pad.atoms[2] != "np_thru_hole":
            if not pad.atoms[1] or not any(layer.endswith(".Cu") for layer in layers[0].atoms[1:]):
                raise DomainError("Pad électrique sans numéro ou couche cuivre.")
            pads.add(pad.atoms[1])
    if not pads:
        raise DomainError("Footprint sans pads électriques.")
    models = []
    for model in tree.children_named("model"):
        if len(model.atoms) != 2 or not model.atoms[1]:
            raise DomainError("Lien 3D incomplet.")
        models.append(model.atoms[1].replace("\\", "/").rsplit("/", 1)[-1])
        for tag in ("scale", "rotate"):
            children = model.children_named(tag)
            if len(children) != 1:
                raise DomainError("Transformation 3D incomplète.")
            numbers(children[0], "xyz", 3, tag == "scale")
        position = model.children_named("offset") or model.children_named("at")
        if len(position) != 1:
            raise DomainError("Position 3D absente ou ambiguë.")
        numbers(position[0], "xyz", 3)
    return tree.atoms[1], tuple(sorted(pads)), tuple(sorted(models))


class LocalResourceProbe:
    def __init__(self, store: LocalAssetStore, index: LocalKiCadIndex) -> None:
        self.store, self.index = store, index

    def managed(self, file: AssetFile) -> Inspection:
        try:
            self.store.verify(file)
            result = self._inspect(
                self.store._path(file),
                file.asset_type,
                file.sha256,
                file.symbol_name,
                file.extension,
            )
            self.store.verify(file)
            return result
        except (DomainError, OSError, UnicodeError) as error:
            return Inspection(file.asset_type, error=str(error))

    def official(self, reference: KiCadReference) -> Inspection:
        try:
            self.index.verify_reference(reference)
            roots = self.index.configuration()
            folder = {
                AssetType.SYMBOL: roots.symbols,
                AssetType.FOOTPRINT: roots.footprints,
                AssetType.MODEL_3D: roots.models,
            }[reference.asset_type]
            path = Path(folder) / reference.relative_path
            result = self._inspect(
                path,
                reference.asset_type,
                reference.sha256,
                reference.name if reference.asset_type is AssetType.SYMBOL else "",
                path.suffix.lower(),
            )
            self.index.verify_reference(reference)
            return result
        except (DomainError, OSError, UnicodeError) as error:
            return Inspection(reference.asset_type, error=str(error))

    def model_links(
        self, file: AssetFile | None, reference: KiCadReference | None
    ) -> tuple[str, ...]:
        # Additional discovery information, deliberately outside M5 fingerprints.
        if file and file.asset_type is AssetType.FOOTPRINT:
            self.store.verify(file)
            path = self.store._path(file)
        elif reference and reference.asset_type is AssetType.FOOTPRINT:
            self.index.verify_reference(reference)
            path = Path(self.index.configuration().footprints) / reference.relative_path
        else:
            return ()
        if path.stat().st_size > 64 * 1024 * 1024:
            raise DomainError("Empreinte trop grande.")
        with path.open("rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise DomainError("Empreinte trop grande.")
        tree = parse(raw.decode("utf-8"))
        footprint_info(tree)
        links = tuple(n.atoms[1].replace("\\", "/") for n in tree.children_named("model"))
        if file:
            self.store.verify(file)
        else:
            assert reference is not None
            self.index.verify_reference(reference)
        return links

    @staticmethod
    def _inspect(
        path: Path, kind: AssetType, digest: str, selected: str, extension: str
    ) -> Inspection:
        if kind in {AssetType.SYMBOL, AssetType.FOOTPRINT}:
            if path.stat().st_size > 64 * 1024 * 1024:
                raise DomainError("S-expression supérieure à 64 Mio.")
            with path.open("rb") as stream:
                data = stream.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise DomainError("S-expression supérieure à 64 Mio.")
            tree = parse(data.decode("utf-8"))
            if kind is AssetType.SYMBOL:
                name, pins, footprint = symbol_info(tree, selected)
                return Inspection(kind, digest, name, pins, footprint)
            name, pads, models = footprint_info(tree)
            return Inspection(kind, digest, name, pads, models=models)
        with path.open("rb") as stream:
            head = stream.read(4096)
            stream.seek(max(0, path.stat().st_size - 4096))
            tail = stream.read(4096)
        if kind is AssetType.MODEL_3D:
            if extension in {".step", ".stp"}:
                if (
                    not head.lstrip().startswith(b"ISO-10303-21;")
                    or b"END-ISO-10303-21;" not in tail
                ):
                    raise DomainError("Enveloppe STEP non reconnue ou tronquée.")
            elif extension == ".wrl":
                if not head.startswith(b"#VRML V2.0 utf8"):
                    raise DomainError("En-tête WRL non reconnu.")
            else:
                raise DomainError("Format 3D non supporté.")
        return Inspection(kind, digest, path.name)
