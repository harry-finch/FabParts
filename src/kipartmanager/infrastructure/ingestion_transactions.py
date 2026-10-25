"""SQLite serialization of a complete ingestion confirmation."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kipartmanager.domain.entities import DomainError
from kipartmanager.infrastructure.catalogue import SqliteCatalogue
from kipartmanager.infrastructure.documentation import SqliteDocumentation
from kipartmanager.infrastructure.models import IngestionOperationRow
from kipartmanager.ports.ingestion import IngestionTransaction, Receipt


class SqliteIngestionTransaction:
    def __init__(self, engine: Engine, session: Session) -> None:
        self.session = session
        self.catalogue = SqliteCatalogue(engine, session)
        self.documentation = SqliteDocumentation(engine, session)

    def receipt(self, operation_id: UUID) -> Receipt | None:
        row = self.session.get(IngestionOperationRow, operation_id)
        return Receipt(row.id, row.request_sha256, row.part_id) if row else None

    def record(self, receipt: Receipt) -> None:
        self.session.add(
            IngestionOperationRow(
                id=receipt.operation_id,
                request_sha256=receipt.request_sha256,
                part_id=receipt.part_id,
            )
        )
        self.session.flush()


class SqliteIngestionTransactions:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def begin(self) -> Iterator[IngestionTransaction]:
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(text("BEGIN IMMEDIATE"))
                yield SqliteIngestionTransaction(self.engine, session)
        except SQLAlchemyError as error:
            raise DomainError("Enregistrement annulé ; aucune confirmation créée.") from error

    def receipt(self, operation_id: UUID) -> Receipt | None:
        with Session(self.engine) as session:
            return SqliteIngestionTransaction(self.engine, session).receipt(operation_id)
