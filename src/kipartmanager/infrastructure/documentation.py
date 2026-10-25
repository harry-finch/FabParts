"""SQLite documentation repository and bounded, explicit local JSON proposals."""

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from kipartmanager.domain.documentation import (
    DocumentKind,
    FieldValue,
    Identification,
    MetadataEvent,
    MetadataField,
    MetadataProposal,
    MetadataSource,
    PartDocument,
)
from kipartmanager.domain.entities import Asset, AssetOrigin, AssetType, ConflictError, DomainError
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.models import (
    DocumentRow,
    IdentificationRow,
    PartRow,
    part_assets,
)
from kipartmanager.infrastructure.sessions import repository_session


def encode(value: Identification | PartDocument) -> str:
    return json.dumps(asdict(value), default=str, ensure_ascii=False, sort_keys=True)


def source_from(data: dict[str, object]) -> MetadataSource:
    return MetadataSource(
        str(data["label"]), str(data["reference"]), AssetOrigin(str(data["origin"]))
    )


def fields_from(data: list[dict[str, str]]) -> tuple[FieldValue, ...]:
    return tuple(FieldValue(MetadataField(v["field"]), v["value"]) for v in data)


def identification_from(raw: str) -> Identification:
    try:
        data = json.loads(raw)
        history = tuple(
            MetadataEvent(
                source_from(e["source"]),
                fields_from(e["before"]),
                fields_from(e["after"]),
                e["recorded_at"],
                UUID(e["id"]),
            )
            for e in data["history"]
        )
        return Identification(
            UUID(data["part_id"]), data["revision"], fields_from(data["values"]), history
        )
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise DomainError("Historique d’identification illisible ; données conservées.") from error


def document_from(raw: str) -> PartDocument:
    try:
        data = json.loads(raw)
        return PartDocument(
            id=UUID(data["id"]),
            part_id=UUID(data["part_id"]),
            asset_id=UUID(data["asset_id"]),
            title=data["title"],
            revision=data["revision"],
            document_date=data["document_date"],
            language=data["language"],
            kind=DocumentKind(data["kind"]),
            recorded_at=data["recorded_at"],
            source=source_from(data["source"]),
        )
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise DomainError("Fiche document illisible ; fichier conservé.") from error


class SqliteDocumentation:
    def __init__(self, engine: Engine, session: Session | None = None) -> None:
        self.engine, self.session = engine, session

    @staticmethod
    def _identification(session: Session, part_id: UUID) -> Identification:
        row = session.get(IdentificationRow, part_id)
        if row is None:
            return Identification(part_id)
        value = identification_from(row.data_json)
        if value.part_id != part_id or value.revision != row.revision:
            raise DomainError("Identité d’historique incohérente.")
        return value

    def identification(self, part_id: UUID) -> Identification:
        with repository_session(self.engine, self.session) as session:
            return self._identification(session, part_id)

    def save_identification(self, value: Identification, expected: Identification) -> None:
        try:
            with repository_session(self.engine, self.session, write=True) as session:
                if session.get(PartRow, value.part_id) is None:
                    raise DomainError("Composant introuvable.")
                if value.part_id != expected.part_id or value.revision != expected.revision + 1:
                    raise DomainError("Révision d’identification incohérente.")
                if self._identification(session, value.part_id) != expected:
                    raise ConflictError(
                        "Identification modifiée ; recharger l’aperçu avant acceptation."
                    )
                session.merge(
                    IdentificationRow(
                        part_id=value.part_id, revision=value.revision, data_json=encode(value)
                    )
                )
        except SQLAlchemyError as error:
            raise DomainError("Identification non enregistrée ; transaction annulée.") from error

    def documents(self, part_id: UUID) -> tuple[PartDocument, ...]:
        with repository_session(self.engine, self.session) as session:
            result = tuple(
                document_from(row.data_json)
                for row in session.scalars(
                    select(DocumentRow).where(DocumentRow.part_id == part_id)
                )
            )
            if any(d.part_id != part_id for d in result):
                raise DomainError("Identité de document incohérente.")
            return tuple(sorted(result, key=lambda d: (d.recorded_at, str(d.id))))

    def add_document(self, document: PartDocument, asset: Asset, *, new_asset: bool) -> None:
        try:
            with repository_session(self.engine, self.session, write=True) as session:
                if session.get(PartRow, document.part_id) is None:
                    raise DomainError("Composant introuvable.")
                if (
                    document.asset_id != asset.id
                    or asset.asset_type is not AssetType.DATASHEET
                    or asset.file is None
                ):
                    raise DomainError("Un PDF géré est requis.")
                from kipartmanager.infrastructure.models import AssetRow

                existing = session.get(AssetRow, asset.id)
                if new_asset:
                    if existing is not None:
                        raise ConflictError("L’asset existe déjà ; aucun fichier remplacé.")
                    SqliteCatalogue._save(session, asset)
                elif (
                    existing is None
                    or SqliteCatalogue(self.engine)._entity(session, existing) != asset
                ):
                    raise ConflictError("Le PDF a changé ; recharger les documents.")
                if (
                    session.scalar(
                        select(part_assets.c.asset_id).where(
                            part_assets.c.part_id == document.part_id,
                            part_assets.c.asset_id == asset.id,
                        )
                    )
                    is None
                ):
                    session.execute(
                        insert(part_assets).values(part_id=document.part_id, asset_id=asset.id)
                    )
                session.add(
                    DocumentRow(
                        id=document.id,
                        part_id=document.part_id,
                        asset_id=asset.id,
                        data_json=encode(document),
                    )
                )
        except IntegrityError as error:
            raise ConflictError(
                "PDF déjà documenté pour ce composant ; aucun fichier remplacé."
            ) from error
        except SQLAlchemyError as error:
            raise DomainError("Document non enregistré ; transaction annulée.") from error


class LocalProposalReader:
    def read(self, source: str) -> MetadataProposal:
        try:
            with Path(source).open("rb") as reader:
                content = reader.read(65537)
            if len(content) > 65536:
                raise DomainError("Proposition JSON trop volumineuse (64 Kio maximum).")
            data = json.loads(content)
            if data["format"] != "kipart-identification/1":
                raise DomainError("Format de proposition non pris en charge.")
            source_data = data["source"]
            if set(source_data) != {"label", "reference", "origin"} or any(
                not isinstance(v, str) for v in source_data.values()
            ):
                raise DomainError("Source de proposition invalide.")
            values = data["fields"]
            if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
                raise DomainError("Champs de proposition invalides.")
            return MetadataProposal(
                source_from(source_data),
                tuple(FieldValue(MetadataField(k), v) for k, v in values.items()),
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise DomainError(f"Proposition JSON non lue : {error}") from error
