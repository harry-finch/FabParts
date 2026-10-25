"""One 3D worker, at most two jobs/snapshots; no catalogue access in the worker."""

import hashlib
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from kipartmanager.application.preview_buffers import PreviewBuffers
from kipartmanager.domain.entities import DomainError
from kipartmanager.ports.previews import (
    HANDLE_TTL,
    PDF_CHUNK,
    PDF_LIMIT,
    MeshConverter,
    PreviewProblem,
)


@dataclass
class ModelJob:
    source: bytes
    expires: float = field(default_factory=lambda: time.monotonic() + HANDLE_TTL)
    cancel: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] = field(default_factory=lambda: {"status": "loading"})
    running: bool = False


class ModelJobs:
    def __init__(self, converter: MeshConverter) -> None:
        self.converter = converter
        self.jobs: OrderedDict[str, ModelJob] = OrderedDict()
        self.buffers = PreviewBuffers()
        self.condition = threading.Condition()
        self.closed = False
        self.worker: threading.Thread | None = None

    def _expire(self) -> None:
        for handle, job in list(self.jobs.items()):
            if job.expires <= time.monotonic():
                self._release(handle)

    def _release(self, handle: str) -> None:
        job = self.jobs.pop(handle, None)
        if job:
            job.cancel.set()
            job.source = b""
        self.buffers.release(handle)

    def start(self, source: bytes) -> str:
        with self.condition:
            if self.closed:
                raise DomainError("Moteur 3D arrêté.")
            if not 0 < len(source) <= PDF_LIMIT:
                raise PreviewProblem("too_large", "Modèle 3D limité à 16 Mio.")
            self._expire()
            while len(self.jobs) >= 2:
                self._release(next(iter(self.jobs)))
            handle = secrets.token_hex(24)
            self.jobs[handle] = ModelJob(source)
            if self.worker is None:
                self.worker = threading.Thread(target=self._work, name="model-preview", daemon=True)
                self.worker.start()
            self.condition.notify_all()
            return handle

    def _work(self) -> None:
        while True:
            with self.condition:
                self._expire()
                if self.closed:
                    return
                pending = next(
                    (
                        (h, j)
                        for h, j in self.jobs.items()
                        if not j.running and j.result["status"] == "loading"
                    ),
                    None,
                )
                if pending is None:
                    self.condition.wait(timeout=1)
                    continue
                handle, job = pending
                job.running = True
                source, job.source = job.source, b""
            try:
                payload, metadata = self.converter(source, job.cancel)
                if not 0 < len(payload) <= PDF_LIMIT:
                    raise PreviewProblem("too_large", "Maillage limité à 16 Mio.")
                result = {
                    "status": "ready",
                    **metadata,
                    "size_bytes": len(payload),
                    "chunk_bytes": PDF_CHUNK,
                    "mesh_sha256": hashlib.sha256(payload).hexdigest(),
                }
            except PreviewProblem as error:
                payload, result = b"", {"status": error.status, "message": str(error)}
            except DomainError as error:
                payload, result = b"", {"status": "error", "message": str(error)}
            except Exception:
                payload, result = b"", {"status": "error", "message": "Conversion 3D échouée."}
            finally:
                source = b""
            with self.condition:
                if not self.closed and not job.cancel.is_set() and self.jobs.get(handle) is job:
                    if payload:
                        self.buffers.put(payload, handle)
                    job.result = result
                payload = b""

    def status(self, handle: str) -> dict[str, Any]:
        with self.condition:
            self._expire()
            job = self.jobs.get(handle)
            if job is None:
                raise DomainError("Session 3D expirée ou annulée.")
            return {**job.result, "handle": handle}

    def chunk(self, handle: str, offset: int) -> dict[str, object]:
        with self.condition:
            self._expire()
            return self.buffers.chunk(handle, offset)

    def release(self, handle: str) -> dict[str, bool]:
        with self.condition:
            self._release(handle)
            self.condition.notify_all()
            return {"released": True}

    def close(self) -> None:
        with self.condition:
            self.closed = True
            for handle in list(self.jobs):
                self._release(handle)
            self.condition.notify_all()
        if self.worker:
            self.worker.join(timeout=1.5)
