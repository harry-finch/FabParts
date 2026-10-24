"""Traceable identification proposals and additive datasheet documentation."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from kipartmanager.domain.entities import AssetOrigin, DomainError


class MetadataField(StrEnum):
    MANUFACTURER = "manufacturer"
    MPN = "mpn"
    CATEGORY = "category"
    NOTES = "notes"


FIELD_LABELS = {
    MetadataField.MANUFACTURER: "Constructeur",
    MetadataField.MPN: "Référence constructeur (MPN)",
    MetadataField.CATEGORY: "Catégorie",
    MetadataField.NOTES: "Notes d’identification",
}


@dataclass(frozen=True)
class MetadataSource:
    label: str
    reference: str
    origin: AssetOrigin = AssetOrigin.USER_PROVIDED

    def __post_init__(self) -> None:
        if not self.label.strip() or not self.reference.strip():
            raise DomainError("Le nom de source et sa référence sont requis pour la traçabilité.")
        if self.origin not in {
            AssetOrigin.USER_PROVIDED,
            AssetOrigin.MANUFACTURER,
            AssetOrigin.TRUSTED_THIRD_PARTY,
            AssetOrigin.GENERATED_AI,
        }:
            raise DomainError("Origine d’identification non prise en charge.")
        if max(len(self.label), len(self.reference)) > 2048:
            raise DomainError("Référence de source trop longue.")


@dataclass(frozen=True)
class FieldValue:
    field: MetadataField
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or len(self.value) > 4096 or "\x00" in self.value:
            raise DomainError("Métadonnée invalide ou trop longue (4 096 caractères maximum).")


@dataclass(frozen=True)
class MetadataProposal:
    source: MetadataSource
    values: tuple[FieldValue, ...]

    def __post_init__(self) -> None:
        if not self.values or len({v.field for v in self.values}) != len(self.values):
            raise DomainError("La proposition doit contenir des champs distincts.")


@dataclass(frozen=True)
class MetadataEvent:
    source: MetadataSource
    before: tuple[FieldValue, ...]
    after: tuple[FieldValue, ...]
    recorded_at: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        try:
            timestamp = datetime.fromisoformat(self.recorded_at)
            if timestamp.tzinfo is None:
                raise ValueError
        except ValueError as error:
            raise DomainError("Horodatage de provenance invalide.") from error


@dataclass(frozen=True)
class Identification:
    part_id: UUID
    revision: int = 0
    values: tuple[FieldValue, ...] = ()
    history: tuple[MetadataEvent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 0:
            raise DomainError("Révision d’identification invalide.")
        if len({v.field for v in self.values}) != len(self.values):
            raise DomainError("Champs d’identification dupliqués.")

    def value(self, field: MetadataField) -> str:
        return next((v.value for v in self.values if v.field is field), "")

    def conflicts(self, proposal: MetadataProposal) -> tuple[MetadataField, ...]:
        return tuple(
            v.field
            for v in proposal.values
            if self.value(v.field) and self.value(v.field) != v.value
        )

    def accept(
        self,
        proposal: MetadataProposal,
        fields: tuple[MetadataField, ...],
        *,
        replace_existing: bool,
        recorded_at: str,
    ) -> "Identification":
        if not fields or len(set(fields)) != len(fields):
            raise DomainError("Choisir au moins un champ distinct à accepter.")
        proposed = {v.field: v for v in proposal.values}
        if any(f not in proposed for f in fields):
            raise DomainError("Champ absent de la proposition.")
        if not replace_existing and set(fields).intersection(self.conflicts(proposal)):
            raise DomainError("Confirmer explicitement le remplacement des valeurs existantes.")
        before = tuple(FieldValue(f, self.value(f)) for f in fields)
        after = tuple(proposed[f] for f in fields)
        current = {v.field: v for v in self.values}
        current.update({v.field: v for v in after})
        event = MetadataEvent(proposal.source, before, after, recorded_at)
        return Identification(
            self.part_id,
            self.revision + 1,
            tuple(current[f] for f in MetadataField if f in current),
            (*self.history, event),
        )


def validate_document_fields(title: str, revision: str, document_date: str, language: str) -> None:
    if not title.strip():
        raise DomainError("Le titre du document est requis.")
    if any(len(v) > 2048 or "\x00" in v for v in (title, revision, language)):
        raise DomainError("Informations du document invalides ou trop longues.")
    if document_date:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date):
                raise ValueError
            date.fromisoformat(document_date)
        except ValueError as error:
            raise DomainError("Date attendue au format AAAA-MM-JJ.") from error


class DocumentKind(StrEnum):
    DATASHEET = "DATASHEET"
    APPLICATION_NOTE = "APPLICATION_NOTE"
    ERRATA = "ERRATA"


@dataclass(frozen=True, kw_only=True)
class PartDocument:
    part_id: UUID
    asset_id: UUID
    title: str
    revision: str = ""
    document_date: str = ""
    language: str = ""
    kind: DocumentKind = DocumentKind.DATASHEET
    recorded_at: str
    source: MetadataSource
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        validate_document_fields(self.title, self.revision, self.document_date, self.language)
        # Same durable timestamp rule as identification events.
        MetadataEvent(self.source, (), (), self.recorded_at)


@dataclass(frozen=True)
class DocumentDetails:
    title: str
    source: MetadataSource
    revision: str = ""
    document_date: str = ""
    language: str = ""
    kind: DocumentKind = DocumentKind.DATASHEET

    def __post_init__(self) -> None:
        validate_document_fields(self.title, self.revision, self.document_date, self.language)

    def record(self, part_id: UUID, asset_id: UUID, recorded_at: str) -> PartDocument:
        return PartDocument(
            part_id=part_id,
            asset_id=asset_id,
            title=self.title,
            source=self.source,
            revision=self.revision,
            document_date=self.document_date,
            language=self.language,
            kind=self.kind,
            recorded_at=recorded_at,
        )
