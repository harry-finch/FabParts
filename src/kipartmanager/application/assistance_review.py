"""Ephemeral M11 consent/review session; only M10 acceptance can persist fields."""

import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from kipartmanager.application.assistance import Assistance
from kipartmanager.application.documentation import Documentation
from kipartmanager.domain.assistance import (
    AssistanceBackend,
    AssistanceConfiguration,
    AssistanceRequest,
)
from kipartmanager.domain.documentation import Identification, MetadataField, MetadataProposal
from kipartmanager.domain.entities import AssetOrigin, DomainError, Part


@dataclass
class AssistanceSession:
    handle: str
    request: AssistanceRequest
    config: AssistanceConfiguration
    expected: Identification
    part: Part
    expires: float
    status: str = "prepared"
    proposal: MetadataProposal | None = None
    cancelled: bool = False


class AssistanceReview:
    def __init__(
        self,
        assistance: Assistance,
        documentation: Documentation,
        protect: Callable[[str], None] = lambda text: None,
    ) -> None:
        self.assistance, self.documentation, self.protect = assistance, documentation, protect
        self.session: AssistanceSession | None = None
        self.lock = threading.Lock()
        self.worker: threading.Thread | None = None

    def configuration(self) -> dict[str, Any]:
        config = self.assistance.configuration()
        self.protect(json.dumps(asdict(config), ensure_ascii=False))
        provider = self.assistance.provider
        available = bool(provider and provider.available(config))
        return {
            **asdict(config),
            "destination": config.destination,
            "availability": "disabled"
            if not config.enabled
            else "configured"
            if available
            else "missing_key",
        }

    def configure(self, enabled: bool, backend: str, endpoint: str, model: str) -> dict[str, Any]:
        config = AssistanceConfiguration(enabled, endpoint, model, AssistanceBackend(backend))
        self.protect(json.dumps(asdict(config), ensure_ascii=False))
        self.close()
        self.assistance.configure(config)
        return self.configuration()

    def identification(self, id: str) -> dict[str, Any]:
        value = self.documentation.identification(UUID(id))
        return {
            "revision": value.revision,
            "values": {f.value: value.value(f) for f in MetadataField},
            "history": [
                {
                    "source": asdict(e.source),
                    "recorded_at": e.recorded_at,
                    "before": [asdict(v) for v in e.before],
                    "after": [asdict(v) for v in e.after],
                }
                for e in value.history[-10:]
            ],
        }

    def prepare(self, id: str, text: str, include: bool) -> dict[str, Any]:
        self.close()
        part_id = UUID(id)
        expected = self.documentation.identification(part_id)
        config = self.assistance.configuration()
        if not config.enabled:
            raise DomainError("Assistance IA désactivée / AI assistance disabled")
        if not self.assistance.provider or not self.assistance.provider.available(config):
            raise DomainError("Fournisseur non configuré / Provider not configured")
        part = self.documentation.catalogue.require(Part, part_id)
        request = AssistanceRequest(
            part_id, expected.revision, text, expected.values if include else ()
        )
        self.protect(request.payload)
        self.protect(json.dumps(asdict(config), ensure_ascii=False))
        session = AssistanceSession(
            secrets.token_hex(24), request, config, expected, part, time.monotonic() + 1200
        )
        self.session = session
        return {
            "handle": session.handle,
            "payload": request.payload,
            "sha256": request.sha256,
            "destination": config.destination,
            "backend": config.backend.value,
            "model": config.model,
            "revision": expected.revision,
        }

    def _current(self, id: str, handle: str) -> AssistanceSession:
        session = self.session
        if (
            not session
            or session.handle != handle
            or str(session.part.id) != id
            or session.cancelled
            or session.expires < time.monotonic()
        ):
            raise DomainError("Session IA expirée ou annulée / AI session expired or cancelled")
        if (
            self.assistance.configuration() != session.config
            or self.documentation.identification(session.part.id) != session.expected
            or self.documentation.catalogue.require(Part, session.part.id) != session.part
        ):
            self.close()
            raise DomainError(
                "Contexte modifié ; préparer à nouveau / Context changed; prepare again"
            )
        return session

    def start(self, id: str, handle: str, consent: bool) -> dict[str, str]:
        session = self._current(id, handle)
        if consent is not True:
            raise DomainError("Autoriser cette requête / Authorize this request")
        with self.lock:
            if session.status != "prepared" or self.worker and self.worker.is_alive():
                raise DomainError(
                    "Une analyse est déjà en cours ou terminée / Analysis already started"
                )
            session.status = "loading"
            self.worker = threading.Thread(
                target=self._work, args=(session,), name="ai-assistance", daemon=True
            )
            self.worker.start()
        return {"status": "loading"}

    def _work(self, session: AssistanceSession) -> None:
        try:
            result = self.assistance.suggest(session.request, session.config, consent=True)
            if result.source.origin is not AssetOrigin.GENERATED_AI or any(
                not isinstance(v.field, MetadataField) for v in result.values
            ):
                raise DomainError("Invalid suggestion")
            self.protect(json.dumps(asdict(result), ensure_ascii=False))
            status = "ready"
        except Exception:
            # Never reflect provider exception bodies, context, raw response or secrets.
            result, status = None, "error"
        with self.lock:
            if self.session is session and not session.cancelled:
                session.proposal, session.status = result, status

    def status(self, id: str, handle: str) -> dict[str, Any]:
        session = self._current(id, handle)
        with self.lock:
            proposal = session.proposal
            return {
                "status": session.status,
                "rows": [
                    {
                        "field": v.field.value,
                        "current": session.expected.value(v.field),
                        "proposed": v.value,
                        "conflict": bool(
                            session.expected.value(v.field)
                            and session.expected.value(v.field) != v.value
                        ),
                    }
                    for v in proposal.values
                ]
                if proposal
                else [],
                "source": asdict(proposal.source) if proposal else None,
            }

    def accept(
        self, id: str, handle: str, fields: list[str], replace_existing: bool
    ) -> dict[str, Any]:
        session = self._current(id, handle)
        if session.status != "ready" or not session.proposal:
            raise DomainError("Aucune proposition à accepter / No proposal to accept")
        self.documentation.accept(
            session.expected,
            session.proposal,
            tuple(MetadataField(f) for f in fields),
            replace_existing=replace_existing,
        )
        self.close()
        return self.identification(id)

    def cancel(self, id: str, handle: str) -> dict[str, bool]:
        session = self.session
        if session and session.handle == handle and str(session.part.id) == id:
            self.close()
        return {"cancelled": True}

    def close(self) -> None:
        with self.lock:
            if self.session:
                self.session.cancelled, self.session.proposal = True, None
            self.session = None
