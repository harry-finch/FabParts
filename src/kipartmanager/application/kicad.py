"""Explicit local index operations; no catalogue mutation or resolver."""

from kipartmanager.domain.entities import AssetType
from kipartmanager.domain.kicad import IndexReport, KiCadError, KiCadReference, LibraryRoots
from kipartmanager.ports.kicad import KiCadIndexPort


class KiCadLibraries:
    def __init__(self, index: KiCadIndexPort) -> None:
        self.index = index

    def configuration(self) -> LibraryRoots:
        return self.index.configuration()

    def configure(self, roots: LibraryRoots) -> None:
        self.index.configure(roots)

    def discover(self) -> LibraryRoots:
        return self.index.discover()

    def rebuild(self) -> IndexReport:
        return self.index.rebuild(self.configuration())

    def report(self) -> IndexReport:
        return self.index.report()

    def search(
        self, text: str, kind: AssetType | None = None, limit: int = 200
    ) -> list[KiCadReference]:
        if not 1 <= limit <= 1000:
            raise KiCadError("Limite de recherche attendue entre 1 et 1000.")
        return self.index.search(text.strip(), kind, limit)

    def reference(self, key: str) -> KiCadReference | None:
        return self.index.reference(key)

    def verify_reference(self, reference: KiCadReference) -> None:
        self.index.verify_reference(reference)
