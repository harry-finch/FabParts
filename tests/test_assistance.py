"""Explicit assistance boundaries, HTTP contracts and acceptance without network."""

import io
import json
from dataclasses import replace
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from kipartmanager.application.assistance import Assistance
from kipartmanager.application.documentation import Documentation
from kipartmanager.domain.assistance import (
    AssistanceBackend,
    AssistanceConfiguration,
    AssistanceRequest,
)
from kipartmanager.domain.documentation import (
    FieldValue,
    MetadataField,
    MetadataProposal,
    MetadataSource,
)
from kipartmanager.domain.entities import AssetOrigin, DomainError, Part
from kipartmanager.infrastructure.assistance import (
    AssistanceToml,
    ChatAssistance,
    NoRedirect,
    parse_suggestions,
)
from kipartmanager.infrastructure.datasheets import ManufacturerSettings
from kipartmanager.infrastructure.documentation import LocalProposalReader, SqliteDocumentation
from tests.test_validation import setup_case

GEMINI = AssistanceConfiguration(
    True,
    "https://generativelanguage.googleapis.com/v1beta",
    "fixture-gemini",
    AssistanceBackend.GEMINI,
)
OLLAMA = AssistanceConfiguration(
    True, "http://127.0.0.1:11434/api/chat", "fixture-local", AssistanceBackend.OLLAMA
)
SECRET = "fixture-api-key-never-persisted"


class FixtureAssistant:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    def available(self, config: AssistanceConfiguration) -> bool:
        return True

    def suggest(
        self, request: AssistanceRequest, config: AssistanceConfiguration
    ) -> MetadataProposal:
        self.calls += 1
        if self.error:
            raise self.error
        return MetadataProposal(
            MetadataSource(
                "IA fixture",
                f"ai:fixture;model={config.model};sha256={request.sha256}",
                AssetOrigin.GENERATED_AI,
            ),
            (
                FieldValue(MetadataField.MPN, "AI-MPN"),
                FieldValue(MetadataField.CATEGORY, "Resistor"),
            ),
        )


def request() -> AssistanceRequest:
    return AssistanceRequest(uuid4(), 0, "Résistance de précision ; marquage R123")


@pytest.mark.parametrize(
    "endpoint,backend",
    [
        ("http://example.com/api/chat", AssistanceBackend.OLLAMA),
        ("http://localhost:11434/api/chat", AssistanceBackend.OLLAMA),
        ("http://127.0.0.1:11434/api/chat?token=secret", AssistanceBackend.OLLAMA),
        ("http://api.example.com/chat/completions", AssistanceBackend.CHAT),
        ("https://user:secret@api.example.com/chat/completions", AssistanceBackend.CHAT),
        ("https://api.example.com/chat/completions?key=secret", AssistanceBackend.CHAT),
        ("https://api.example.com/other", AssistanceBackend.CHAT),
    ],
)
def test_invalid_destinations(endpoint: str, backend: AssistanceBackend) -> None:
    with pytest.raises(DomainError):
        AssistanceConfiguration(True, endpoint, "model", backend)


def test_configuration_consent_absence_and_exact_destination(tmp_path: Path) -> None:
    settings = AssistanceToml(tmp_path)
    provider = FixtureAssistant()
    service = Assistance(settings, provider)
    assert service.configuration() == AssistanceConfiguration()
    with pytest.raises(DomainError, match="Confirmer"):
        service.suggest(request(), GEMINI)
    with pytest.raises(DomainError, match="modifiée"):
        service.suggest(request(), GEMINI, consent=True)
    with pytest.raises(DomainError, match="désactivée"):
        service.suggest(request(), service.configuration(), consent=True)
    service.configure(GEMINI)
    assert service.configuration() == GEMINI
    service.provider = None
    with pytest.raises(DomainError, match="non configuré"):
        service.suggest(request(), GEMINI, consent=True)
    assert provider.calls == 0
    service.configure(OLLAMA)
    assert settings.load() == OLLAMA
    settings.path.write_text("broken")
    with pytest.raises(DomainError, match="illisible"):
        settings.load()
    settings.save(AssistanceConfiguration())
    assert not settings.load().enabled


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"values":{"mpn":"X"}}\n```',
        '{"values":{"unknown":"X"}}',
        '{"values":{"mpn":4}}',
        '{"values":{"mpn":""}}',
        '{"values":{"mpn":"X","mpn":"Y"}}',
        '{"values":{"mpn":"X"},"execute":"command"}',
        '{"values":[]}',
        '{"values":{"mpn":"\\ud800"}}',
        '{"values":{"notes":"' + "x" * 4097 + '"}}',
    ],
)
def test_invalid_structured_output(raw: str) -> None:
    with pytest.raises(DomainError, match="invalide"):
        parse_suggestions(raw)


def test_untrusted_context_and_empty_suggestions() -> None:
    value = request()
    assert str(value.part_id) not in value.payload
    assert "revision" not in value.payload
    assert parse_suggestions('{"values":{}}') == ()
    assert len(value.sha256) == 64
    with pytest.raises(DomainError):
        replace(value, text="x" * 16001)


@pytest.mark.parametrize("config", [GEMINI, OLLAMA])
def test_http_contract_and_secret_routing(
    config: AssistanceConfiguration, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kipartmanager.infrastructure.assistance as module

    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("KIPART_AI_API_KEY", "other-key")
    captured: list[Any] = []
    raw = json.dumps({"values": {"mpn": "X-123"}})
    envelope = (
        {"message": {"content": raw}, "done": True, "done_reason": "stop"}
        if config.backend is AssistanceBackend.OLLAMA
        else {"choices": [{"message": {"content": raw}, "finish_reason": "stop"}]}
    )

    if config.backend is AssistanceBackend.GEMINI:
        envelope = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": raw}]}}]}

    class Response(io.BytesIO):
        pass

    class Opener:
        def open(self, req: Any, timeout: int) -> Response:
            captured.append(req)
            return Response(json.dumps(envelope).encode())

    monkeypatch.setattr(module, "build_opener", lambda *handlers: Opener())
    service = ChatAssistance()
    assert service.available(config)
    proposal = service.suggest(request(), config)
    req = captured[0]
    body = json.loads(req.data)
    assert req.full_url == config.destination and req.get_method() == "POST"
    if config.backend is not AssistanceBackend.GEMINI:
        assert body["stream"] is False
    if config.backend is AssistanceBackend.GEMINI:
        assert req.get_header("X-goog-api-key") == SECRET
        assert body["generationConfig"]["responseMimeType"] == "application/json"
    elif config.backend is AssistanceBackend.OLLAMA:
        assert req.get_header("Authorization") is None
        assert body["format"] == "json" and "store" not in body
    else:
        assert req.get_header("Authorization") == "Bearer " + SECRET
        assert body["store"] is False and body["response_format"] == {"type": "json_object"}
    assert SECRET not in req.data.decode()
    assert proposal.source.origin is AssetOrigin.GENERATED_AI
    assert config.model in proposal.source.reference
    assert proposal.values[0].value == "X-123"
    assert SECRET not in proposal.source.reference


@pytest.mark.parametrize(
    "case",
    ["offline", "429", "401", "truncated", "refusal", "secret", "huge", "empty", "wrong-fields"],
)
def test_http_failure_no_data_or_secret_exposure(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kipartmanager.infrastructure.assistance as module

    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    raw = '{"values":{"mpn":"X"}}'
    envelope: dict[str, Any] = {"choices": [{"message": {"content": raw}, "finish_reason": "stop"}]}
    if case == "truncated":
        envelope["choices"][0]["finish_reason"] = "length"
    if case == "refusal":
        envelope["choices"][0]["message"]["refusal"] = "refused"
    if case == "secret":
        envelope["choices"][0]["message"]["content"] = json.dumps({"values": {"notes": SECRET}})
    if case == "empty":
        envelope["choices"][0]["message"]["content"] = '{"values":{}}'
    if case == "wrong-fields":
        envelope["choices"][0]["message"]["content"] = '{"values":{"command":"rm"}}'

    class Opener:
        def open(self, req: Any, timeout: int) -> io.BytesIO:
            if case == "offline":
                raise URLError(SECRET)
            if case in ("401", "429"):
                raise HTTPError(req.full_url, int(case), SECRET, Message(), None)
            return io.BytesIO(b"x" * 300000 if case == "huge" else json.dumps(envelope).encode())

    monkeypatch.setattr(module, "build_opener", lambda *handlers: Opener())
    with pytest.raises(DomainError) as caught:
        ChatAssistance().suggest(
            request(),
            replace(
                GEMINI,
                endpoint="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                backend=AssistanceBackend.CHAT,
            ),
        )
    assert SECRET not in str(caught.value)


def test_redirect_and_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not ChatAssistance().available(GEMINI)
    with pytest.raises(DomainError, match="absent"):
        ChatAssistance().suggest(request(), GEMINI)
    with pytest.raises(DomainError, match="Redirection"):
        NoRedirect().redirect_request(None, None, 302, "secret", None, "https://other.test")  # type: ignore[arg-type]


def test_proposal_rejection_partial_acceptance_provenance_and_stale_guard(
    tmp_path: Path, engine: Engine
) -> None:
    validation, _, part, _, _, _ = setup_case(tmp_path, engine)
    docs = Documentation(
        validation.catalogue,
        SqliteDocumentation(engine),
        LocalProposalReader(),
        ManufacturerSettings(tmp_path),
    )
    settings = AssistanceToml(tmp_path)
    settings.save(GEMINI)
    provider = FixtureAssistant()
    service = Assistance(settings, provider)
    part = validation.catalogue.require(Part, part.id)
    expected = docs.identification(part.id)
    suggestion = service.suggest(replace(request(), part_id=part.id), GEMINI, consent=True)
    # Generate and discard without any catalogue writes.
    assert docs.identification(part.id) == expected
    updated = docs.accept(expected, suggestion, (MetadataField.CATEGORY,))
    assert updated.value(MetadataField.MPN) == ""
    assert updated.history[0].source.origin is AssetOrigin.GENERATED_AI
    assert SqliteDocumentation(engine).identification(part.id) == updated
    with pytest.raises(DomainError):
        docs.accept(expected, suggestion, (MetadataField.MPN,))
    assert validation.catalogue.require(Part, part.id) == part
    provider.error = RuntimeError(SECRET)
    with pytest.raises(DomainError) as caught:
        service.suggest(request(), GEMINI, consent=True)
    assert SECRET not in str(caught.value)
    assert docs.identification(part.id) == updated


@pytest.mark.parametrize(
    "envelope",
    [
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]},
        {
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": '{"values":{}}'}]}}
            ]
        },
    ],
)
def test_gemini_native_unusable_response(
    envelope: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import kipartmanager.infrastructure.assistance as module

    monkeypatch.setenv("GEMINI_API_KEY", SECRET)

    class Opener:
        def open(self, req: Any, timeout: int) -> io.BytesIO:
            return io.BytesIO(json.dumps(envelope).encode())

    monkeypatch.setattr(module, "build_opener", lambda *handlers: Opener())
    with pytest.raises(DomainError):
        ChatAssistance().suggest(request(), GEMINI)


def test_revoked_activation_discards_in_flight_suggestions(tmp_path: Path) -> None:
    settings = AssistanceToml(tmp_path)
    settings.save(GEMINI)

    class RevokingAssistant(FixtureAssistant):
        def suggest(
            self, context: AssistanceRequest, config: AssistanceConfiguration
        ) -> MetadataProposal:
            result = super().suggest(context, config)
            settings.save(replace(config, enabled=False))
            return result

    service = Assistance(settings, RevokingAssistant())
    with pytest.raises(DomainError, match="pendant"):
        service.suggest(request(), GEMINI, consent=True)


@pytest.mark.parametrize(
    "config",
    [
        GEMINI,
        OLLAMA,
        AssistanceConfiguration(True, "https://api.example/chat/completions", "fixture"),
    ],
)
@pytest.mark.parametrize(
    "status,code",
    [
        (400, "bad_request"),
        (401, "authentication"),
        (403, "permission"),
        (404, "model_or_endpoint"),
        (429, "rate_limit"),
        (500, "provider_unavailable"),
        (418, "http_error"),
    ],
)
def test_safe_http_diagnostics(
    config: AssistanceConfiguration, status: int, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kipartmanager.infrastructure.assistance as module
    from kipartmanager.domain.assistance import AssistanceFailure

    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("KIPART_AI_API_KEY", SECRET)

    class Body(io.BytesIO):
        def read(self, *args: Any, **kwargs: Any) -> bytes:
            raise AssertionError("Never read an error body")

    class Opener:
        def open(self, req: Any, timeout: int) -> io.BytesIO:
            raise HTTPError(req.full_url, status, SECRET, Message(), Body(SECRET.encode()))

    monkeypatch.setattr(module, "build_opener", lambda *handlers: Opener())
    with pytest.raises(AssistanceFailure) as caught:
        ChatAssistance().suggest(request(), config)
    assert caught.value.code.value == code and caught.value.http_status == status
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize(
    "case,code",
    [
        ("timeout", "timeout"),
        ("wrapped_timeout", "timeout"),
        ("network", "network"),
        ("empty", "no_suggestions"),
        ("invalid", "invalid_response"),
        ("blocked", "blocked"),
        ("truncated", "incomplete"),
        ("huge", "too_large"),
    ],
)
def test_safe_response_diagnostics(case: str, code: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kipartmanager.infrastructure.assistance as module
    from kipartmanager.domain.assistance import AssistanceFailure

    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    envelope: dict[str, Any] = {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"values":{}}'}]}}]
    }
    if case == "invalid":
        envelope["candidates"][0]["content"]["parts"][0]["text"] = SECRET
    if case == "blocked":
        envelope = {"promptFeedback": {"blockReason": "SAFETY"}}
    if case == "truncated":
        envelope["candidates"][0]["finishReason"] = "MAX_TOKENS"

    class Opener:
        def open(self, req: Any, timeout: int) -> io.BytesIO:
            if case == "timeout":
                raise TimeoutError(SECRET)
            if case == "wrapped_timeout":
                raise URLError(TimeoutError(SECRET))
            if case == "network":
                raise URLError(SECRET)
            return io.BytesIO(b"x" * 300000 if case == "huge" else json.dumps(envelope).encode())

    monkeypatch.setattr(module, "build_opener", lambda *handlers: Opener())
    with pytest.raises(AssistanceFailure) as caught:
        ChatAssistance().suggest(request(), GEMINI)
    assert caught.value.code.value == code and caught.value.http_status is None
    assert SECRET not in str(caught.value)
