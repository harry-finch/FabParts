"""Atomic choice and managed association persistence."""

from typing import Protocol

from kipartmanager.domain.entities import Package, Part
from kipartmanager.domain.resolution import ResourceChoice


class ResolutionRepository(Protocol):
    def choices(self, owner: Part | Package) -> tuple[ResourceChoice, ...]: ...
    def choose(
        self, owner: Part | Package, choice: ResourceChoice, expected: ResourceChoice | None
    ) -> None: ...
