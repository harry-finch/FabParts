"""Durable scoped reports, separate from global asset state."""

import json
from dataclasses import asdict

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kipartmanager.domain.entities import Collection, DomainError, Part
from kipartmanager.domain.validation import Finding, Level, ValidationReport
from kipartmanager.infrastructure.models import ValidationRow


def key(subject: Part | Collection) -> str:
    return f"{type(subject).__name__}:{subject.id.hex}"


class SqliteValidationReports:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def load_report(self, subject: Part | Collection) -> ValidationReport | None:
        try:
            with Session(self.engine) as session:
                row = session.get(ValidationRow, key(subject))
                if row is None:
                    return None
                data = json.loads(row.report_json)
                if data["subject_key"] != key(subject):
                    raise ValueError("Sujet du rapport incompatible.")
                data["findings"] = tuple(
                    Finding(
                        code=f["code"],
                        level=Level(f["level"]),
                        message=f["message"],
                        resource_key=f["resource_key"],
                        sha256=f["sha256"],
                    )
                    for f in data["findings"]
                )
                return ValidationReport(**data)
        except (SQLAlchemyError, ValueError, KeyError, TypeError) as error:
            raise DomainError(
                "Rapport de validation illisible ; revalider explicitement."
            ) from error

    def save_report(self, subject: Part | Collection, report: ValidationReport) -> None:
        if report.subject_key != key(subject):
            raise DomainError("Sujet du rapport incompatible.")
        try:
            with Session(self.engine) as session, session.begin():
                session.merge(
                    ValidationRow(
                        subject_key=key(subject),
                        part_id=subject.id if isinstance(subject, Part) else None,
                        collection_id=subject.id if isinstance(subject, Collection) else None,
                        report_json=json.dumps(asdict(report), sort_keys=True, ensure_ascii=False),
                    )
                )
        except SQLAlchemyError as error:
            raise DomainError("Rapport non enregistré ; ancienne validation conservée.") from error
