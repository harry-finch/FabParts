"""Bounded private staging; publication is exclusively AssetImports' responsibility."""

import hashlib
import os
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from kipartmanager.domain.asset_files import FORMATS, AssetFile
from kipartmanager.domain.entities import AssetType, DomainError
from kipartmanager.infrastructure.readonly_previews import ReadonlyPreviews
from kipartmanager.ports.prepared_files import PreparedFile
from kipartmanager.ports.previews import PreviewContent

FILE_LIMIT = 16 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
FILE_COUNT = 8
PREPARATION_TTL = 20 * 60


@dataclass
class Transfer:
    filename: str
    size: int
    received: int = 0
    prepared: PreparedFile | None = None


@dataclass
class Preparation:
    created: float
    transfers: dict[str, Transfer] = field(default_factory=dict)


class LocalPreparedFiles:
    def __init__(self, root: Path, previews: ReadonlyPreviews) -> None:
        self.root = root / "preparations"
        self.previews = previews
        self.sessions: dict[str, Preparation] = {}

    def _session(self, preparation: str) -> Preparation:
        for key, value in tuple(self.sessions.items()):
            if time.monotonic() - value.created > PREPARATION_TTL:
                self.cancel(key)
        if preparation not in self.sessions:
            raise DomainError("Préparation expirée ou annulée ; recommencer l’ajout.")
        return self.sessions[preparation]

    def _transfer(self, preparation: str, handle: str) -> Transfer:
        session = self._session(preparation)
        if handle not in session.transfers:
            raise DomainError("Fichier non autorisé dans cette préparation.")
        return session.transfers[handle]

    def begin(self) -> str:
        # One wizard per engine; an abandoned preparation cannot accumulate disk usage.
        self.close()
        handle = secrets.token_hex(24)
        (self.root / handle).mkdir(mode=0o700)
        self.sessions[handle] = Preparation(time.monotonic())
        return handle

    def start(self, preparation: str, filename: str, size: int) -> str:
        session = self._session(preparation)
        extension = Path(filename).suffix.lower()
        if len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise DomainError("Nom de fichier invalide.")
        AssetFile("0" * 64, size, extension, filename)
        if extension not in FORMATS or type(size) is not int or not 0 < size <= FILE_LIMIT:
            raise DomainError("Format refusé ou fichier supérieur à 16 Mio.")
        if (
            len(session.transfers) >= FILE_COUNT
            or sum(t.size for t in session.transfers.values()) + size > TOTAL_LIMIT
        ):
            raise DomainError("Préparation limitée à 8 fichiers et 64 Mio.")
        handle = secrets.token_hex(24)
        (self.root / preparation / handle).touch(mode=0o600, exist_ok=False)
        session.transfers[handle] = Transfer(filename, size)
        return handle

    def append(self, preparation: str, handle: str, offset: int, data: bytes) -> None:
        transfer = self._transfer(preparation, handle)
        if transfer.prepared or offset != transfer.received or not 0 < len(data) <= 8192:
            raise DomainError("Bloc de transfert invalide ou hors ordre.")
        if transfer.received + len(data) > transfer.size:
            raise DomainError("Fichier modifié pendant la lecture.")
        fd = os.open(self.root / preparation / handle, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(fd, "ab") as writer:
            writer.write(data)
        transfer.received += len(data)

    def content(self, preparation: str, handle: str) -> bytes:
        transfer = self._transfer(preparation, handle)
        fd = os.open(self.root / preparation / handle, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as reader:
            data = reader.read(FILE_LIMIT + 1)
        if len(data) != transfer.size or len(data) > FILE_LIMIT:
            raise DomainError("Transfert incomplet ou fichier modifié.")
        if transfer.prepared and hashlib.sha256(data).hexdigest() != transfer.prepared.file.sha256:
            raise DomainError("Fichier préparé modifié ; recommencer la sélection.")
        return data

    def finish(self, preparation: str, handle: str, sha256: str, symbol: str = "") -> PreparedFile:
        transfer = self._transfer(preparation, handle)
        data = self.content(preparation, handle)
        if transfer.received != transfer.size or hashlib.sha256(data).hexdigest() != sha256:
            raise DomainError("Empreinte du transfert incorrecte.")
        file = AssetFile(
            sha256, len(data), Path(transfer.filename).suffix.lower(), transfer.filename
        )
        content = self.previews.read(
            self.root / preparation, handle, file.sha256, file.asset_type, symbol
        )
        if file.asset_type is AssetType.DATASHEET and b"%%EOF" not in data[-4096:]:
            raise DomainError("PDF incomplet : fin de document absente.")
        if file.asset_type is AssetType.MODEL_3D:
            if file.extension == ".wrl":
                if not data.lstrip().startswith(b"#VRML V2.0 utf8"):
                    raise DomainError("Le fichier ne contient pas un modèle VRML 2.")
            elif not data.lstrip().startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in data:
                raise DomainError("Le fichier ne contient pas un document STEP complet.")
        symbols = (
            ((symbol,) if symbol else tuple(dict.fromkeys(d.name for d in content.drawings)))
            if (file.asset_type is AssetType.SYMBOL)
            else ()
        )
        if file.asset_type in {AssetType.SYMBOL, AssetType.FOOTPRINT} and not content.drawings:
            raise DomainError("Aucune représentation KiCad lisible.")
        transfer.prepared = PreparedFile(handle, file, symbols)
        return transfer.prepared

    def files(self, preparation: str) -> tuple[PreparedFile, ...]:
        return tuple(
            t.prepared for t in self._session(preparation).transfers.values() if t.prepared
        )

    def preview(self, preparation: str, handle: str, symbol: str = "") -> PreviewContent:
        prepared = self._transfer(preparation, handle).prepared
        if prepared is None:
            raise DomainError("Le transfert doit être terminé.")
        if symbol and symbol not in prepared.symbols:
            raise DomainError("Entrée absente de la bibliothèque de symboles.")
        return self.previews.read(
            self.root / preparation, handle, prepared.file.sha256, prepared.file.asset_type, symbol
        )

    def discard(self, preparation: str, handle: str) -> None:
        self._transfer(preparation, handle)
        (self.root / preparation / handle).unlink()
        del self.sessions[preparation].transfers[handle]

    def cancel(self, preparation: str) -> None:
        if preparation in self.sessions:
            shutil.rmtree(self.root / preparation)
            del self.sessions[preparation]

    def close(self) -> None:
        for preparation in tuple(self.sessions):
            self.cancel(preparation)
