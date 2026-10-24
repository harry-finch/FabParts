"""Scoped validation findings and publication eligibility; no adapters."""

from dataclasses import dataclass
from enum import StrEnum

from kipartmanager.domain.entities import AssetType, DomainError

RULESET = "M5-1"


class Level(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Finding:
    code: str
    level: Level
    message: str
    resource_key: str = ""
    sha256: str = ""


@dataclass(frozen=True)
class Inspection:
    asset_type: AssetType
    sha256: str = ""
    name: str = ""
    numbers: tuple[str, ...] = ()
    footprint: str = ""
    models: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class ValidationReport:
    subject_key: str
    fingerprint: str
    created_at: str
    findings: tuple[Finding, ...]
    warnings_accepted: bool = False
    ruleset: str = RULESET

    def __post_init__(self) -> None:
        if (
            len(self.fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in self.fingerprint)
            or type(self.warnings_accepted) is not bool
            or not self.findings
        ):
            raise DomainError("Rapport ou empreinte de validation invalide.")

    @property
    def level(self) -> Level:
        if any(f.level is Level.ERROR for f in self.findings):
            return Level.ERROR
        if any(f.level is Level.WARNING for f in self.findings):
            return Level.WARNING
        return Level.PASS

    @property
    def eligible(self) -> bool:
        return self.level is Level.PASS or (self.level is Level.WARNING and self.warnings_accepted)


@dataclass(frozen=True)
class Qualification:
    report: ValidationReport | None
    stale: bool = False

    @property
    def state(self) -> str:
        return (
            "UNCHECKED"
            if self.report is None
            else "STALE"
            if self.stale
            else self.report.level.value
        )

    @property
    def eligible(self) -> bool:
        return self.report is not None and not self.stale and self.report.eligible


def connection_findings(symbol: Inspection, footprint: Inspection) -> tuple[Finding, ...]:
    missing = set(symbol.numbers) - set(footprint.numbers)
    result = [
        Finding(
            "PIN_PAD",
            Level.ERROR if missing else Level.PASS,
            "Pins absentes du footprint : " + ", ".join(sorted(missing))
            if missing
            else "Tous les numéros de pins ont un pad correspondant.",
        )
    ]
    extra = set(footprint.numbers) - set(symbol.numbers)
    if extra:
        result.append(
            Finding(
                "EXTRA_PADS",
                Level.WARNING,
                "Pads sans pin correspondante : " + ", ".join(sorted(extra)),
            )
        )
    if symbol.footprint and symbol.footprint.split(":")[-1] != footprint.name.split(":")[-1]:
        result.append(
            Finding(
                "FOOTPRINT_HINT",
                Level.WARNING,
                "Le footprint choisi diffère de la propriété Footprint du symbole.",
            )
        )
    return tuple(result)
