"""Transfer published libraries; adapters own ZIP and persistence transactions."""

from kipartmanager.domain.bundles import BundlePreview
from kipartmanager.domain.publication import Publication
from kipartmanager.ports.bundles import BundleTransport


class Bundles:
    def __init__(self, transport: BundleTransport) -> None:
        self.transport = transport

    def export(self, publication: Publication, destination: str) -> None:
        self.transport.export(publication, destination)

    def inspect(self, source: str) -> BundlePreview:
        return self.transport.inspect(source)

    def import_bundle(self, source: str) -> BundlePreview:
        return self.transport.import_bundle(source)
