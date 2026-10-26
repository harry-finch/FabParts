"""Optional M9/M10 operations: one bounded worker, no catalogue writes in the worker.

Only polling a live preparation can expose downloaded bytes to existing staging.
A cancelled/expired job can never publish an Asset or change a selection.
"""

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from kipartmanager.application.documentation import Documentation
from kipartmanager.application.ingestion import Ingestion
from kipartmanager.application.remote_kicad import RemoteLibraries
from kipartmanager.domain.datasheets import DatasheetConfiguration, DatasheetDownload
from kipartmanager.domain.entities import AssetOrigin, AssetType, DomainError
from kipartmanager.domain.remote_kicad import (
    REPOSITORIES,
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteSearch,
    verify_download,
)
from kipartmanager.ports.previews import HANDLE_TTL


@dataclass
class ExternalJob:
    handle: str
    preparation: str
    config: tuple[RemoteConfiguration, DatasheetConfiguration]
    expires: float
    output: object = None
    error: str = ""
    done: bool = False
    cancelled: bool = False
    presented: dict[str, Any] | None = None


class ExternalSources:
    def __init__(self, ingestion: Ingestion, remote: RemoteLibraries, documents: Documentation):
        self.ingestion, self.remote, self.documents = ingestion, remote, documents
        self.lock = threading.Lock()
        self.worker: threading.Thread | None = None
        self.job: ExternalJob | None = None
        self.candidates: dict[str, RemoteCandidate] = {}
        self.candidate_preparation = ""
        self.candidate_config: RemoteConfiguration | None = None

    def configuration(self) -> dict[str, Any]:
        return {
            "kicad": asdict(self.remote.configuration()),
            "pdf": asdict(self.documents.configuration()),
        }

    def configure(
        self, source: str, enabled: bool, revision: str, domains: list[str]
    ) -> dict[str, Any]:
        self.close()
        if source == "kicad":
            self.remote.configure(RemoteConfiguration(enabled, revision))
        else:
            self.documents.configure(DatasheetConfiguration(enabled, tuple(domains)))
        return self.configuration()

    def _configs(self) -> tuple[RemoteConfiguration, DatasheetConfiguration]:
        return self.remote.configuration(), self.documents.configuration()

    def _start(self, preparation: str, operation: Callable[[], object]) -> dict[str, str]:
        self.ingestion._preparation(preparation)
        config = self._configs()
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise DomainError(
                    "Une requête réseau est encore en cours ; continuer localement ou réessayer."
                )
            job = ExternalJob(
                secrets.token_hex(24), preparation, config, time.monotonic() + HANDLE_TTL
            )
            self.job = job
            self.worker = threading.Thread(
                target=self._work, args=(job, operation), name="external-source", daemon=True
            )
            self.worker.start()
        return {"handle": job.handle, "status": "loading"}

    def _work(self, job: ExternalJob, operation: Callable[[], object]) -> None:
        try:
            output, error = operation(), ""
        except DomainError as problem:
            output, error = None, str(problem)
        except Exception:
            output, error = (
                None,
                "Source indisponible ; les ressources locales restent disponibles.",
            )
        with self.lock:
            if not job.cancelled and time.monotonic() < job.expires:
                job.output, job.error, job.done = output, error, True

    def search(self, preparation: str, role: str, library: str, query: str) -> dict[str, str]:
        kind = AssetType(role)
        if kind not in REPOSITORIES or not library.strip() or not query.strip():
            raise DomainError("Type, bibliothèque précise et terme recherché requis.")
        self.remote.require_enabled()
        return self._start(preparation, lambda: self.remote.search(kind, library, query))

    def download(self, preparation: str, token: str) -> dict[str, str]:
        candidate = self.candidates.get(token)
        if (
            candidate is None
            or self.candidate_preparation != preparation
            or self.remote.require_enabled() != self.candidate_config
        ):
            raise DomainError("Candidat expiré ou configuration modifiée ; relancer la recherche.")

        def download() -> RemoteDownload:
            result = self.remote.download(candidate)
            if result.candidate != candidate:
                raise DomainError(
                    "Candidat modifié pendant le téléchargement ; relancer la recherche."
                )
            verify_download(result)
            return result

        return self._start(preparation, download)

    def pdf(self, preparation: str, url: str, consent: bool) -> dict[str, str]:
        if consent is not True:
            raise DomainError("Autorisation explicite requise pour ce téléchargement PDF.")
        self.documents.configuration().authorize(url)

        def download() -> DatasheetDownload:
            result = self.documents.download(url)
            if result.url != url:
                raise DomainError("URL du document modifiée ; téléchargement refusé.")
            return result

        return self._start(preparation, download)

    def status(self, preparation: str, handle: str) -> dict[str, Any]:
        self.ingestion._preparation(preparation)
        configs = self._configs()
        with self.lock:
            job = self.job
            if (
                job is None
                or job.handle != handle
                or job.preparation != preparation
                or job.cancelled
                or time.monotonic() >= job.expires
                or job.config != configs
            ):
                if job and job.handle == handle:
                    job.cancelled, job.output = True, None
                raise DomainError("Requête expirée, annulée ou configuration modifiée.")
            if job.presented is not None:
                return job.presented
            if not job.done:
                return {"status": "loading", "handle": handle}
            if job.error:
                job.presented = {"status": "error", "message": job.error}
                return job.presented
            output, job.output = job.output, None
            try:
                if isinstance(output, RemoteSearch):
                    self.candidates = {secrets.token_hex(24): c for c in output.candidates[:200]}
                    self.candidate_preparation = preparation
                    self.candidate_config = configs[0]
                    result: dict[str, Any] = {
                        "candidates": [
                            {
                                **asdict(c),
                                "token": token,
                                "source": c.source,
                                "availability": "download_required",
                            }
                            for token, c in self.candidates.items()
                        ],
                        "notices": list(output.notices)[:20],
                    }
                elif isinstance(output, RemoteDownload):
                    c = output.candidate
                    result = self.ingestion.stage_external(
                        preparation,
                        output.content,
                        c.path.rsplit("/", 1)[-1],
                        c.identifier,
                        AssetOrigin.KICAD_OFFICIAL,
                        c.source,
                        c.name if c.asset_type is AssetType.SYMBOL else "",
                    )
                elif isinstance(output, DatasheetDownload):
                    result = self.ingestion.stage_external(
                        preparation,
                        output.content,
                        output.filename,
                        output.filename,
                        AssetOrigin.MANUFACTURER,
                        output.url,
                    )
                else:
                    raise DomainError("Réponse de source invalide.")
                job.presented = {"status": "ready", **result}
            except DomainError as error:
                job.presented = {"status": "error", "message": str(error)}
            return job.presented

    def cancel(self, preparation: str, handle: str) -> dict[str, bool]:
        self.ingestion._preparation(preparation)
        with self.lock:
            job = self.job
            if not job or job.handle != handle or job.preparation != preparation:
                raise DomainError("Requête hors préparation.")
            job.cancelled, job.output, job.presented = True, None, None
        return {"cancelled": True}

    def close(self) -> None:
        with self.lock:
            if self.job:
                self.job.cancelled, self.job.output, self.job.presented = True, None, None
            self.candidates.clear()
            self.candidate_preparation = ""
            self.candidate_config = None
