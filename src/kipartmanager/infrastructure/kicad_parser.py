"""Bounded S-expression reader for library metadata, not semantic validation."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from kipartmanager.domain.kicad import KiCadError


@dataclass
class Node:
    atoms: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    quoted: set[int] = field(default_factory=set)
    order: list[tuple[bool, int]] = field(default_factory=list)

    def children_named(self, name: str) -> list["Node"]:
        return [child for child in self.children if child.atoms and child.atoms[0] == name]

    def value(self, name: str) -> str:
        matches = self.children_named(name)
        if len(matches) > 1:
            raise KiCadError(f"Champ dupliqué : {name}")
        return matches[0].atoms[1] if matches and len(matches[0].atoms) > 1 else ""


def tokens(text: str) -> Iterator[tuple[str, str]]:
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char == ";":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
        elif char in "()":
            yield char, char
            index += 1
        elif char == '"':
            index += 1
            value: list[str] = []
            while index < len(text) and text[index] != '"':
                char = text[index]
                if char == "\\":
                    index += 1
                    if index >= len(text):
                        raise KiCadError("Échappement incomplet.")
                    char = {"n": "\n", "r": "\r", "t": "\t"}.get(text[index], text[index])
                value.append(char)
                index += 1
            if index >= len(text):
                raise KiCadError("Chaîne non terminée.")
            yield "string", "".join(value)
            index += 1
        else:
            start = index
            while index < len(text) and not text[index].isspace() and text[index] not in '();"':
                index += 1
            yield "atom", text[start:index]


def parse(text: str) -> Node:
    stack: list[Node] = []
    root: Node | None = None
    for token, value in tokens(text):
        if token == "(":
            node = Node()
            if stack:
                stack[-1].order.append((False, len(stack[-1].children)))
                stack[-1].children.append(node)
            elif root is not None:
                raise KiCadError("Plusieurs racines S-expression.")
            else:
                root = node
            stack.append(node)
            if len(stack) > 128:
                raise KiCadError("Imbrication excessive.")
        elif token == ")":
            if not stack or not stack[-1].atoms:
                raise KiCadError("Parenthèse inattendue ou expression vide.")
            stack.pop()
        elif stack:
            stack[-1].order.append((True, len(stack[-1].atoms)))
            if token == "string":
                stack[-1].quoted.add(len(stack[-1].atoms))
            stack[-1].atoms.append(value)
        else:
            raise KiCadError("Atome hors expression.")
    if root is None or stack:
        raise KiCadError("S-expression vide ou non terminée.")
    return root


def check_version(root: Node, symbol: bool) -> str:
    expected = "kicad_symbol_lib" if symbol else "footprint"
    if root.atoms[0] != expected:
        raise KiCadError(f"Format non supporté : {root.atoms[0]}")
    version = root.value("version")
    lower, upper = ("20211014", "20251024") if symbol else ("20210108", "20260206")
    try:
        if len(version) != 8 or not version.isdigit():
            raise ValueError
        datetime.strptime(version, "%Y%m%d")
    except ValueError as error:
        raise KiCadError("Version KiCad absente ou invalide.") from error
    if not lower <= version <= upper:
        raise KiCadError(f"Version non supportée : {version} (attendu {lower}–{upper})")
    return version


def symbol_metadata(node: Node) -> tuple[str, str]:
    properties = {
        child.atoms[1]: child.atoms[2]
        for child in node.children_named("property")
        if len(child.atoms) >= 3
    }
    return (
        properties.get("Description", properties.get("ki_description", "")),
        properties.get("ki_keywords", ""),
    )
