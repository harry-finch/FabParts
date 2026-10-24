"""Immutable publication identity and its frozen build inputs."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from kipartmanager.domain.build import BuildPlan
from kipartmanager.domain.entities import DomainError
from kipartmanager.domain.validation import ValidationReport

BUILDER_VERSION = "M6-1"
MANIFEST_VERSION = 1


def validate_version(version: int) -> None:
    if type(version) is not int or not 1 <= version <= 999999:
        raise DomainError("Version de publication invalide (1–999999).")


@dataclass(frozen=True)
class Publication:
    collection_id: UUID
    collection_name: str
    version: int
    created_at: str
    fingerprint: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        validate_version(self.version)
        if not isinstance(self.collection_id, UUID) or not self.collection_name:
            raise DomainError("Identité de publication invalide.")
        for digest in (self.fingerprint, self.manifest_sha256):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise DomainError("Empreinte de publication invalide.")
        if datetime.fromisoformat(self.created_at).utcoffset() is None:
            raise DomainError("Horodatage de publication sans fuseau.")


@dataclass(frozen=True)
class PublicationSnapshot:
    plan: BuildPlan
    validation: ValidationReport

    def __post_init__(self) -> None:
        if (
            not self.plan.parts
            or not self.validation.eligible
            or self.validation.fingerprint != self.plan.fingerprint
            or self.validation.subject_key != f"Collection:{self.plan.collection_id.hex}"
        ):
            raise DomainError("Instantané de collection non qualifié.")
