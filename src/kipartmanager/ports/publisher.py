"""Construction of a new standalone output folder from qualified inputs."""

from collections.abc import Callable
from typing import Protocol

from kipartmanager.domain.build import BuildPlan, BuildResult


class LibraryBuilder(Protocol):
    def build(
        self, plan: BuildPlan, destination: str, confirm: Callable[[], None]
    ) -> BuildResult: ...
