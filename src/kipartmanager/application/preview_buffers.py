"""Small bounded snapshot store shared by PDF and mesh transports (IPC v1)."""

import base64
import secrets
import time
from collections import OrderedDict
from typing import Any

from kipartmanager.domain.entities import DomainError
from kipartmanager.ports.previews import HANDLE_TTL, MAX_HANDLES, PDF_CHUNK, PDF_LIMIT


class PreviewBuffers:
    def __init__(self) -> None:
        self.handles: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def expire(self) -> None:
        for handle, (expires, _) in list(self.handles.items()):
            if expires <= time.monotonic():
                del self.handles[handle]

    def put(self, data: bytes, handle: str = "") -> str:
        self.expire()
        if not 0 < len(data) <= PDF_LIMIT:
            raise DomainError("Aperçu limité à 16 Mio.")
        handle = handle or secrets.token_hex(24)
        while len(self.handles) >= MAX_HANDLES:
            self.handles.popitem(last=False)
        self.handles[handle] = (time.monotonic() + HANDLE_TTL, data)
        return handle

    def chunk(self, handle: str, offset: int) -> dict[str, Any]:
        self.expire()
        entry = self.handles.get(handle)
        if entry is None:
            raise DomainError("Aperçu expiré. Rouvrez le document.")
        data = entry[1]
        if not 0 <= offset < len(data) or offset % PDF_CHUNK:
            raise DomainError("Position de bloc invalide.")
        block = data[offset : offset + PDF_CHUNK]
        return {
            "offset": offset,
            "data": base64.b64encode(block).decode("ascii"),
            "eof": offset + len(block) == len(data),
        }

    def release(self, handle: str) -> None:
        self.handles.pop(handle, None)
        self.expire()
