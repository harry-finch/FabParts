"""Bounded read capability: copied Asset Store and configured KiCad roots only.

No store initialization, indexing, import, temporary file or configuration write.
"""

import hashlib
import os
import stat
from collections import OrderedDict
from pathlib import Path

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.infrastructure.kicad_index import LocalKiCadIndex
from kipartmanager.infrastructure.kicad_parser import selected_symbol_library
from kipartmanager.infrastructure.kicad_preview import drawings
from kipartmanager.ports.previews import PDF_LIMIT, PreviewContent, PreviewProblem


class ReadonlyPreviews:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.cache: OrderedDict[tuple[str, AssetType, str], PreviewContent] = OrderedDict()

    def read(
        self, root: Path, relative: str, digest: str, kind: AssetType, selected: str = ""
    ) -> PreviewContent:
        limit = PDF_LIMIT if kind in {AssetType.DATASHEET, AssetType.MODEL_3D} else 8 * 1024 * 1024
        try:
            target = root / relative
            if Path(relative).is_absolute() or not target.resolve().is_relative_to(root):
                raise PreviewProblem(
                    "inaccessible", "Chemin de ressource hors du périmètre autorisé."
                )
            # Nonblocking prevents a malicious FIFO from blocking before fstat.
            fd = os.open(
                target.resolve(strict=True),
                os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise PreviewProblem(
                        "inaccessible", "La ressource doit être un fichier régulier."
                    )
                if info.st_size > limit:
                    raise PreviewProblem(
                        "too_large", f"Aperçu limité à {limit // 1024 // 1024} Mio."
                    )
                data = stream.read(limit + 1)
        except FileNotFoundError as error:
            raise PreviewProblem("missing", "Ressource introuvable") from error
        except OSError as error:
            raise PreviewProblem("inaccessible", "Ressource inaccessible en lecture.") from error
        if len(data) > limit:
            raise PreviewProblem("too_large", "Fichier trop volumineux.")
        if hashlib.sha256(data).hexdigest() != digest:
            raise PreviewProblem(
                "error", "Fichier modifié ou corrompu : empreinte SHA-256 différente."
            )
        if kind is AssetType.MODEL_3D:
            return PreviewContent(model_source=data)
        if kind is AssetType.DATASHEET:
            if not data.startswith(b"%PDF-"):
                raise PreviewProblem("error", "Document PDF invalide : en-tête non reconnu.")
            return PreviewContent(pdf=data)
        if kind not in {AssetType.SYMBOL, AssetType.FOOTPRINT}:
            raise PreviewProblem("unsupported", "Format non pris en charge par cet aperçu.")
        key = (digest, kind, selected)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        try:
            text = data.decode("utf-8")
            if kind is AssetType.SYMBOL and selected:
                text = selected_symbol_library(text, selected, 100000)
            if text.count("(") > 100000:
                raise PreviewProblem(
                    "too_large", "Fichier KiCad trop complexe (100 000 expressions maximum)."
                )
            result = PreviewContent(
                drawings=drawings(text, kind, selected, max_drawings=64, max_primitives=5000)
            )
        except UnicodeError as error:
            raise PreviewProblem("error", "Fichier KiCad non UTF-8.") from error
        except DomainError as error:
            if "Trop" in str(error) or "trop" in str(error):
                raise PreviewProblem("too_large", str(error)) from error
            if "support" in str(error):
                raise PreviewProblem("unsupported", str(error)) from error
            raise
        if len(result.drawings) > 64 or sum(len(d.primitives) for d in result.drawings) > 5000:
            raise PreviewProblem(
                "too_large", "Aperçu trop complexe : 64 représentations, 5 000 primitives maximum."
            )
        if sum(len(p.points) + len(p.text) for d in result.drawings for p in d.primitives) > 100000:
            raise PreviewProblem("too_large", "Géométrie ou textes trop complexes.")
        # Cache only parsed geometry; recheck bytes/hash on every fresh request.
        while len(self.cache) >= 4:
            self.cache.popitem(last=False)
        self.cache[key] = result
        return result

    def managed(self, file: AssetFile) -> PreviewContent:
        root = self.root / "assets"
        if not root.resolve().is_relative_to(self.root):
            raise PreviewProblem("inaccessible", "Asset Store hors de la copie contrôlée.")
        return self.read(
            root.resolve(), file.relative_key, file.sha256, file.asset_type, file.symbol_name
        )

    def official(self, reference: KiCadReference) -> PreviewContent:
        config = self.root / "config/kicad.toml"
        if not config.resolve().is_relative_to(self.root) or (
            config.exists() and config.stat().st_size > 16384
        ):
            raise PreviewProblem("inaccessible", "Configuration KiCad hors limites.")
        roots = LocalKiCadIndex(self.root).configuration()
        folder = {
            AssetType.SYMBOL: roots.symbols,
            AssetType.FOOTPRINT: roots.footprints,
            AssetType.MODEL_3D: roots.models,
        }.get(reference.asset_type)
        if not folder:
            raise PreviewProblem("missing", "Ressource introuvable : dossier KiCad non configuré.")
        return self.read(
            Path(folder).expanduser().resolve(),
            reference.relative_path,
            reference.sha256,
            reference.asset_type,
            reference.name,
        )
