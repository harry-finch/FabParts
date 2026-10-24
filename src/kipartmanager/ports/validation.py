"""Resource inspection and durable scoped reports."""

from typing import Protocol

from kipartmanager.domain.asset_files import AssetFile
from kipartmanager.domain.entities import Collection, Part
from kipartmanager.domain.kicad import KiCadReference
from kipartmanager.domain.validation import Inspection, ValidationReport


class ResourceProbe(Protocol):
    def managed(self, file: AssetFile) -> Inspection: ...
    def official(self, reference: KiCadReference) -> Inspection: ...


class ValidationRepository(Protocol):
    def load_report(self, subject: Part | Collection) -> ValidationReport | None: ...
    def save_report(self, subject: Part | Collection, report: ValidationReport) -> None: ...
