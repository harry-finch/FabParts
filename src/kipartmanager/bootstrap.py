"""Composition root and command-line entry point."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kipartmanager import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Parse options, create the desktop window and run the Qt event loop."""
    parser = argparse.ArgumentParser(prog="kipartmanager")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-dir", type=Path, help="Dossier des données locales")
    options = parser.parse_args(argv)

    # Keep package imports and --help/--version independent of GUI initialization.
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication

    from kipartmanager.application.asset_imports import AssetImports
    from kipartmanager.application.assistance import Assistance
    from kipartmanager.application.bundles import Bundles
    from kipartmanager.application.catalogue import Catalogue
    from kipartmanager.application.documentation import Documentation
    from kipartmanager.application.kicad import KiCadLibraries
    from kipartmanager.application.previews import Previews
    from kipartmanager.application.publications import Publications
    from kipartmanager.application.publisher import LocalPublisher
    from kipartmanager.application.remote_kicad import RemoteLibraries
    from kipartmanager.application.resolver import LocalResolver
    from kipartmanager.application.third_party_assets import ThirdPartyResolver
    from kipartmanager.application.validation import LocalValidation
    from kipartmanager.infrastructure.asset_store import LocalAssetStore
    from kipartmanager.infrastructure.assistance import AssistanceToml, ChatAssistance
    from kipartmanager.infrastructure.bundles import LocalBundles
    from kipartmanager.infrastructure.catalogue import SqliteCatalogue
    from kipartmanager.infrastructure.database import create_database_engine, migrate
    from kipartmanager.infrastructure.datasheets import ManufacturerPDFs, ManufacturerSettings
    from kipartmanager.infrastructure.documentation import LocalProposalReader, SqliteDocumentation
    from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
    from kipartmanager.infrastructure.library_builder import LocalLibraryBuilder
    from kipartmanager.infrastructure.preview_reader import LocalPreviewReader
    from kipartmanager.infrastructure.publications import LocalPublications
    from kipartmanager.infrastructure.remote_kicad import OfficialGitLab, TomlRemoteSettings
    from kipartmanager.infrastructure.resource_probe import LocalResourceProbe
    from kipartmanager.infrastructure.snapmagic import (
        EnvironmentCredential,
        SnapMagicAdapter,
        SnapMagicSettings,
        ThirdPartyInspector,
    )
    from kipartmanager.infrastructure.validation_reports import SqliteValidationReports
    from kipartmanager.ui.branding import PRODUCT_NAME, application_icon
    from kipartmanager.ui.main_window import MainWindow

    app = QApplication([sys.argv[0]])
    app.setApplicationName("KiPart Manager")
    # Keep the historical storage identity so existing catalogues remain discoverable.
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(application_icon())
    app.setDesktopFileName("kipartmanager")
    data_dir = options.data_dir or Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    engine = create_database_engine(data_dir / "database" / "catalogue.sqlite3")
    try:
        migrate(engine)
        store = LocalAssetStore(data_dir / "assets")
        repository = SqliteCatalogue(engine)
        catalogue = Catalogue(repository, store)
        index = LocalKiCadIndex(data_dir)
        libraries = KiCadLibraries(index)
        catalogue.initialize_defaults()
        validation = LocalValidation(
            catalogue, LocalResourceProbe(store, index), SqliteValidationReports(engine)
        )
        builder = LocalLibraryBuilder(store, index, data_dir)
        publisher = LocalPublisher(catalogue, validation, builder)
        publication_store = LocalPublications(data_dir / "publications", builder)
        publications = Publications(publisher, publication_store)
        imports = AssetImports(catalogue, store)
        remote = RemoteLibraries(TomlRemoteSettings(data_dir), imports, OfficialGitLab())
        window = MainWindow(
            catalogue,
            imports,
            libraries,
            LocalResolver(catalogue, repository, libraries),
            validation,
            publisher,
            publications,
            Bundles(LocalBundles(repository, publication_store)),
            previews=Previews(catalogue, LocalPreviewReader(store, index)),
            remote_libraries=remote,
            assistance=Assistance(AssistanceToml(data_dir), ChatAssistance()),
            third_party=ThirdPartyResolver(
                catalogue,
                SnapMagicSettings(data_dir),
                ThirdPartyInspector(),
                SnapMagicAdapter(EnvironmentCredential()),
            ),
            documentation=Documentation(
                catalogue,
                SqliteDocumentation(engine),
                LocalProposalReader(),
                ManufacturerSettings(data_dir),
                ManufacturerPDFs(),
            ),
        )
        window.show()
        return app.exec()
    finally:
        engine.dispose()
