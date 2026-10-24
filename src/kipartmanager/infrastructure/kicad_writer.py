"""Deterministic edits of existing KiCad syntax, preserving quoted atoms/order."""

import copy
import re

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.kicad_parser import Node, check_version, parse
from kipartmanager.infrastructure.resource_probe import footprint_info, symbol_info


def string(value: str) -> str:
    return (
        '"'
        + value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        + '"'
    )


def serialize(node: Node, depth: int = 0) -> str:
    order = node.order or [(True, i) for i in range(len(node.atoms))] + [
        (False, i) for i in range(len(node.children))
    ]
    items = []
    for atom, index in order:
        if atom:
            value = node.atoms[index]
            items.append(string(value) if index in node.quoted else value)
        else:
            items.append("\n" + "  " * (depth + 1) + serialize(node.children[index], depth + 1))
    return "(" + " ".join(items) + ")"


def reorder(node: Node) -> None:
    node.order = []


def property_value(node: Node, key: str, value: str) -> None:
    matches = [
        p for p in node.children_named("property") if len(p.atoms) >= 2 and p.atoms[1] == key
    ]
    if len(matches) > 1:
        raise DomainError(f"Propriété dupliquée : {key}.")
    if matches:
        prop = matches[0]
        if len(prop.atoms) < 3:
            raise DomainError("Propriété incomplète.")
        prop.atoms[2] = value
        prop.quoted.add(2)
    else:
        # KiCad 6 requires a field id; newer readers also accept it.
        ids = {"Footprint": 2, "Datasheet": 3, "Value": 1}
        node.children.append(
            parse(
                f"(property {string(key)} {string(value)} (id {ids[key]}) "
                "(at 0 0 0) (effects (font (size 1.27 1.27)) hide))"
            )
        )
        reorder(node)


def portable_fields(node: Node) -> None:
    """Refuse unresolved file properties outside the PCB resources supported here."""
    for prop in node.children_named("property"):
        if (
            len(prop.atoms) >= 3
            and prop.atoms[1] in {"Sim.Library", "Spice_Lib_File"}
            and prop.atoms[2]
        ):
            raise DomainError("Dépendance de simulation externe non prise en charge en M6.")


def symbols(
    tree: Node, selected: str, output_name: str, footprint: str, value: str, datasheet: str
) -> list[Node]:
    symbol_info(tree, selected)
    entries = {node.atoms[1]: node for node in tree.children_named("symbol")}
    selected = selected or next(iter(entries))
    chain = []
    name = selected
    while name:
        chain.append(name)
        name = entries[name].value("extends")
    names = {
        name: output_name if index == 0 else f"{output_name}__base_{index}"
        for index, name in enumerate(chain)
    }
    result = []
    for name in reversed(chain):
        node = copy.deepcopy(entries[name])
        node.atoms[1] = names[name]
        node.quoted.add(1)
        if node.value("extends"):
            node.children_named("extends")[0].atoms[1] = names[node.value("extends")]
            node.children_named("extends")[0].quoted.add(1)
        for unit in node.children_named("symbol"):
            if len(unit.atoms) != 2 or not re.fullmatch(
                re.escape(name) + r"_\d+_\d+", unit.atoms[1]
            ):
                raise DomainError("Nom d'unité de symbole non pris en charge.")
            unit.atoms[1] = names[name] + unit.atoms[1][len(name) :]
            unit.quoted.add(1)
        property_value(node, "Footprint", footprint)
        property_value(node, "Datasheet", datasheet)
        if name == selected:
            property_value(node, "Value", value)
        portable_fields(node)
        result.append(node)
    return result


def footprint(tree: Node, output_name: str, model_name: str, model_uri: str) -> Node:
    footprint_info(tree)
    node = copy.deepcopy(tree)
    node.atoms[1] = output_name
    node.quoted.add(1)
    links = node.children_named("model")
    if links and not model_uri:
        raise DomainError("Liens 3D sans modèle choisi : résoudre le Package avant construction.")
    if model_uri and not links:
        raise DomainError(
            "Modèle choisi sans transformation dans le footprint ; association 3D à préciser."
        )
    for link in links:
        original = link.atoms[1].replace("\\", "/").rsplit("/", 1)[-1]
        if original != model_name:
            raise DomainError(
                "Lien 3D ambigu ou différent du modèle choisi ; aucun remplacement implicite."
            )
        link.atoms[1] = model_uri
        link.quoted.add(1)
    return node


def library(trees: list[Node], entries: list[Node]) -> Node:
    versions = [check_version(tree, True) for tree in trees]
    for tree in trees:
        if any(
            c.atoms[0] not in {"version", "generator", "generator_version", "symbol"}
            for c in tree.children
        ):
            raise DomainError("Métadonnées racine de bibliothèque non prises en charge.")
    root = parse(f"(kicad_symbol_lib (version {max(versions)}) (generator kipartmanager))")
    root.children.extend(entries)
    reorder(root)
    return root
