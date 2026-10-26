"""Lossless table edits: scan spans, validate syntax, replace only an owned lib node."""

from dataclasses import dataclass

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.kicad_parser import Node, parse
from kipartmanager.infrastructure.kicad_writer import string

LIMIT = 4 * 1024 * 1024
NAMES = ("sym-lib-table", "fp-lib-table")
ROOTS = ("sym_lib_table", "fp_lib_table")


def uncomment(text: str, *, target: str = "") -> str:
    """Legacy DSN accepts # lines; KiCad 10's table PEG grammar accepts none."""
    result = list(text)
    quoted = escaped = comment = False
    line_blank = True
    for i, char in enumerate(text):
        if comment:
            if char in "\r\n":
                comment = False
            else:
                result[i] = " "
                continue
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ";" or (char == "#" and (not line_blank or target == "10.0")):
            raise ValueError("unsupported table comment syntax")
        elif char == "#":
            comment = True
            result[i] = " "
        if char in "\r\n":
            line_blank = True
        elif not char.isspace():
            line_blank = False
    return "".join(result)


def table_parse(text: str) -> Node:
    return parse(uncomment(text))


def spans(text: str) -> tuple[list[tuple[int, int]], int]:
    """Direct-child spans; comments/strings cannot introduce parentheses."""
    result = []
    depth = 0
    quoted = escaped = comment = False
    start = end = 0
    for i, c in enumerate(uncomment(text)):
        if comment:
            if c in "\r\n":
                comment = False
            continue
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
            continue
        if c == ";":
            comment = True
        elif c == '"':
            quoted = True
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2:
                result.append((start, i + 1))
            if depth == 1:
                end = i
            depth -= 1
    return result, end


@dataclass(frozen=True)
class Table:
    raw: bytes
    entries: dict[str, tuple[int, int, str]]
    end: int

    @classmethod
    def read(cls, raw: bytes | None, kind: int, target: str = "") -> "Table":
        raw = raw if raw is not None else f"({ROOTS[kind]}\n)\n".encode()
        if len(raw) > LIMIT or b"\x00" in raw:
            raise DomainError("TABLE_FORMAT: table too large or binary")
        try:
            text = raw.decode("utf-8")
            root = parse(uncomment(text, target=target))
            if root.atoms != [ROOTS[kind]]:
                raise ValueError("root")
            if len(root.children_named("version")) > 1:
                raise ValueError("duplicate table version")
            ranges, end = spans(text)
            if len(ranges) != len(root.children):
                raise ValueError("spans")
            entries = {}
            for child, (a, b) in zip(root.children, ranges, strict=True):
                if child.atoms == ["version"]:
                    raise ValueError("version")
                if child.atoms[0] == "version":
                    if child.atoms != ["version", "7"] or child.children:
                        raise ValueError("unsupported table version")
                    continue
                if child.atoms != ["lib"]:
                    raise ValueError("unknown root field")
                fields = [c.atoms[0] for c in child.children]
                if (
                    len(fields) != len(set(fields))
                    or not {"name", "type", "uri"} <= set(fields)
                    or not set(fields)
                    <= {"name", "type", "uri", "options", "descr", "hidden", "disabled"}
                    or any(
                        c.children
                        or len(c.atoms) != (1 if c.atoms[0] in {"hidden", "disabled"} else 2)
                        for c in child.children
                    )
                ):
                    raise ValueError("lib fields")
                name = child.value("name")
                if not name or name in entries:
                    raise ValueError("duplicate nickname")
                entries[name] = (a, b, child.value("uri"))
            return cls(raw, entries, end)
        except (ValueError, UnicodeError, IndexError) as error:
            raise DomainError("TABLE_FORMAT: unsupported or malformed KiCad table") from error

    def updated(self, kind: int, nickname: str, uri: str, owned: str | None) -> bytes:
        text = self.raw.decode("utf-8")
        existing = self.entries.get(nickname)
        if existing:
            a, b, _ = existing
            if not self.owns(nickname, owned):
                raise DomainError("NICKNAME_COLLISION: entry is not the unchanged FabParts entry")
        elif owned is not None:
            raise DomainError("TABLE_CHANGED: managed entry removed externally")
        node = (
            f'(lib (name {string(nickname)}) (type "KiCad") (uri {string(uri)}) '
            '(options "") (descr "FabParts managed"))'
        )
        if existing:
            # Keep original options, description, extension fields and inline comments.
            a, b, _ = existing
            entry = text[a:b]
            children, _ = spans(entry)
            uri_span = next(
                (x, y) for x, y in children if table_parse(entry[x:y]).atoms[0] == "uri"
            )
            x, y = uri_span
            node = entry[:x] + f"(uri {string(uri)})" + entry[y:]
            updated = text[:a] + node + text[b:]
        else:
            newline = "\r\n" if "\r\n" in text else "\n"
            updated = text[: self.end] + "  " + node + newline + text[self.end :]
        result = updated.encode("utf-8")
        table = Table.read(result, kind)
        if table.entries[nickname][2] != uri:
            raise DomainError("TABLE_FORMAT: URI edit verification failed")
        return result

    def owns(self, nickname: str, owned: str | None) -> bool:
        current = self.entry(nickname)
        if current is None or owned is None:
            return False
        # KiCad may reformat tables. Ownership survives whitespace/comments/order,
        # but never a changed URI, option, flag, plugin, or description.
        left, right = table_parse(current), table_parse(owned)
        return left.atoms == right.atoms and {c.atoms[0]: c.atoms[1:] for c in left.children} == {
            c.atoms[0]: c.atoms[1:] for c in right.children
        }

    def entry(self, nickname: str) -> str | None:
        span = self.entries.get(nickname)
        return self.raw.decode("utf-8")[span[0] : span[1]] if span else None
