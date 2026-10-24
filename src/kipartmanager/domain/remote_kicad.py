"""Unselected official remote candidates; no network or persistence implementation."""

import hashlib
import re
from dataclasses import dataclass

from kipartmanager.domain.entities import AssetType, DomainError

REPOSITORIES = {
    AssetType.SYMBOL: "kicad-symbols",
    AssetType.FOOTPRINT: "kicad-footprints",
    AssetType.MODEL_3D: "kicad-packages3d",
}


class RemoteError(DomainError):
    """Optional remote lookup failure; local services remain usable."""


def simple_name(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and not any(c in value for c in "/\\:\x00\n\r")


@dataclass(frozen=True)
class RemoteConfiguration:
    enabled: bool = False
    revision: str = "9.0.0"

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,80}", self.revision
        ):
            raise RemoteError("Révision attendue : tag, branche simple ou commit Git.")


@dataclass(frozen=True)
class RemoteCandidate:
    asset_type: AssetType
    library: str
    name: str
    path: str
    revision: str
    commit: str
    blob: str = ""
    sha256: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.asset_type not in REPOSITORIES or not all(
            simple_name(v) for v in (self.library, self.name)
        ):
            raise RemoteError("Identité distante invalide.")
        RemoteConfiguration(revision=self.revision)
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit):
            raise RemoteError("Commit distant invalide.")
        suffix = {AssetType.SYMBOL: ".kicad_sym", AssetType.FOOTPRINT: ".kicad_mod"}.get(
            self.asset_type
        )
        expected = (
            f"{self.library}.kicad_sym"
            if self.asset_type is AssetType.SYMBOL
            else f"{self.library}.pretty/{self.name}.kicad_mod"
            if self.asset_type is AssetType.FOOTPRINT
            else f"{self.library}.3dshapes/{self.name}"
        )
        if self.path != expected or (suffix and not self.path.endswith(suffix)):
            raise RemoteError("Chemin officiel distant invalide.")
        if self.asset_type is AssetType.MODEL_3D and not self.name.lower().endswith(
            (".step", ".stp", ".wrl")
        ):
            raise RemoteError("Modèle 3D distant non supporté.")
        if self.sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise RemoteError("SHA-256 distant invalide.")
        if self.blob and not re.fullmatch(r"[0-9a-f]{40}", self.blob):
            raise RemoteError("Identité blob invalide.")
        if not self.sha256 and not self.blob:
            raise RemoteError("Empreinte distante requise.")

    @property
    def identifier(self) -> str:
        return f"{self.library}:{self.name}"

    @property
    def source(self) -> str:
        from urllib.parse import quote

        repository = REPOSITORIES[self.asset_type]
        return (
            f"https://gitlab.com/kicad/libraries/{repository}/-/blob/"
            f"{self.commit}/{quote(self.path, safe='/')}?ref={quote(self.revision, safe='')}"
        )


@dataclass(frozen=True)
class RemoteSearch:
    candidates: tuple[RemoteCandidate, ...] = ()
    notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemoteDownload:
    candidate: RemoteCandidate
    content: bytes


def verify_download(download: RemoteDownload) -> None:
    content, candidate = download.content, download.candidate
    if not content or len(content) > 32 * 1024 * 1024:
        raise RemoteError("Téléchargement vide ou trop volumineux.")
    if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise RemoteError("Pointeur Git LFS non pris en charge ; aucun modèle importé.")
    if candidate.sha256 and hashlib.sha256(content).hexdigest() != candidate.sha256:
        raise RemoteError("SHA-256 différent du candidat ; relancer la recherche.")
    blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
    if candidate.blob and blob != candidate.blob:
        raise RemoteError("Contenu distant différent du blob Git annoncé.")
