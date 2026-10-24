"""Read-only GitLab official libraries adapter, bounded HTTP and local TOML settings."""

import hashlib
import json
import os
import re
import tempfile
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from kipartmanager.domain.entities import AssetType
from kipartmanager.domain.remote_kicad import (
    REPOSITORIES,
    RemoteCandidate,
    RemoteConfiguration,
    RemoteDownload,
    RemoteError,
    RemoteSearch,
    simple_name,
    verify_download,
)
from kipartmanager.infrastructure.kicad_parser import check_version, parse, symbol_metadata

MAX_FILE = 32 * 1024 * 1024
MAX_JSON = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise RemoteError("Redirection distante refusée ; source officielle attendue.")


def fetch(url: str, limit: int) -> bytes:
    """Only URLs built by this adapter are fetched; no credentials or retry loop."""
    try:
        request = Request(
            url, headers={"User-Agent": "KiPartManager-M9", "Accept-Encoding": "identity"}
        )
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            deadline = time.monotonic() + 20
            content = bytearray()
            while True:
                chunk = response.read(min(65536, limit + 1 - len(content)))
                content.extend(chunk)
                if len(content) > limit:
                    raise RemoteError("Réponse distante trop volumineuse.")
                if time.monotonic() > deadline:
                    raise RemoteError("Délai de téléchargement dépassé.")
                if not chunk:
                    return bytes(content)
    except HTTPError as error:
        message = {
            404: "Bibliothèque, chemin ou révision introuvable.",
            429: "Limite GitLab atteinte ; réessayer plus tard.",
        }.get(error.code, f"Erreur HTTP {error.code} de la source officielle.")
        raise RemoteError(message) from error
    except (URLError, OSError) as error:
        raise RemoteError(
            "Source distante inaccessible (réseau, TLS ou délai). Ressources locales conservées."
        ) from error


class TomlRemoteSettings:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "config" / "remote-kicad.toml"

    def load(self) -> RemoteConfiguration:
        try:
            if not self.path.exists():
                return RemoteConfiguration()
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            return RemoteConfiguration(enabled=data["enabled"], revision=data["revision"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RemoteError(
                "Configuration distante illisible ; corriger ou enregistrer à nouveau."
            ) from error

    def save(self, config: RemoteConfiguration) -> None:
        staging: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as writer:
                staging = writer.name
                writer.write(
                    f'enabled = {str(config.enabled).lower()}\nrevision = "{config.revision}"\n'
                )
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(staging, self.path)
        except OSError as error:
            raise RemoteError("Impossible d’enregistrer la configuration distante.") from error
        finally:
            if staging is not None:
                Path(staging).unlink(missing_ok=True)


class OfficialGitLab:
    def __init__(self, get: Callable[[str, int], bytes] = fetch) -> None:
        self.get = get

    @staticmethod
    def base(kind: AssetType) -> str:
        if kind not in REPOSITORIES:
            raise RemoteError(
                "Source officielle disponible pour symboles, footprints et modèles 3D."
            )
        project = quote(f"kicad/libraries/{REPOSITORIES[kind]}", safe="")
        return f"https://gitlab.com/api/v4/projects/{project}/repository"

    def json(self, url: str) -> object:
        content = self.get(url, MAX_JSON)
        try:
            return json.loads(content)
        except (ValueError, UnicodeError) as error:
            raise RemoteError("Réponse JSON GitLab invalide.") from error

    def raw(self, candidate: RemoteCandidate) -> bytes:
        return self.get(
            f"{self.base(candidate.asset_type)}/files/{quote(candidate.path, safe='')}/raw?"
            + urlencode({"ref": candidate.commit}),
            MAX_FILE,
        )

    def search(self, revision: str, kind: AssetType, library: str, query: str) -> RemoteSearch:
        RemoteConfiguration(revision=revision)
        if not simple_name(library):
            raise RemoteError("Nom de bibliothèque invalide.")
        base = self.base(kind)
        info = self.json(f"{base}/commits/{quote(revision, safe='')}")
        if not isinstance(info, dict) or not isinstance(info.get("id"), str):
            raise RemoteError("Révision GitLab invalide.")
        commit = info["id"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise RemoteError("Commit GitLab invalide.")
        deadline = time.monotonic() + 45
        notices: tuple[str, ...]
        candidates: list[RemoteCandidate] = []
        query = query.casefold()
        if kind is AssetType.SYMBOL:
            path = f"{library}.kicad_sym"
            content = self.get(
                f"{base}/files/{quote(path, safe='')}/raw?" + urlencode({"ref": commit}), MAX_FILE
            )
            try:
                root = parse(content.decode("utf-8"))
                check_version(root, True)
                for node in root.children_named("symbol"):
                    if len(node.atoms) != 2:
                        raise RemoteError("Entrée de symbole invalide.")
                    name = node.atoms[1]
                    description, keywords = symbol_metadata(node)
                    if query in f"{name} {description} {keywords}".casefold():
                        candidates.append(
                            RemoteCandidate(
                                kind,
                                library,
                                name,
                                path,
                                revision,
                                commit,
                                sha256=hashlib.sha256(content).hexdigest(),
                                description=description,
                            )
                        )
            except UnicodeError as error:
                raise RemoteError("Bibliothèque de symboles non UTF-8.") from error
            notices = ("Bibliothèque précise ; fichier complet conservé pour l’héritage.",)
        else:
            path = library + (".pretty" if kind is AssetType.FOOTPRINT else ".3dshapes")
            notices = ()
            for page in range(1, 21):
                if time.monotonic() > deadline:
                    raise RemoteError("Délai de recherche dépassé ; préciser la bibliothèque.")
                entries = self.json(
                    f"{base}/tree?"
                    + urlencode({"ref": commit, "path": path, "per_page": 100, "page": page})
                )
                if not isinstance(entries, list):
                    raise RemoteError("Liste GitLab invalide.")
                for item in entries:
                    if not isinstance(item, dict) or not all(
                        isinstance(item.get(k), str) for k in ("name", "path", "id", "type")
                    ):
                        raise RemoteError("Entrée GitLab invalide.")
                    if item["type"] != "blob":
                        continue
                    filename = item["name"]
                    suffixes = (
                        (".kicad_mod",)
                        if kind is AssetType.FOOTPRINT
                        else (".step", ".stp", ".wrl")
                    )
                    if filename.lower().endswith(suffixes) and query in filename.casefold():
                        name = filename[:-10] if kind is AssetType.FOOTPRINT else filename
                        candidates.append(
                            RemoteCandidate(
                                kind, library, name, item["path"], revision, commit, blob=item["id"]
                            )
                        )
                if len(entries) < 100:
                    break
            else:
                notices = (
                    "Arborescence limitée à 2 000 entrées ; résultats éventuellement incomplets.",
                )
        candidates.sort(key=lambda c: c.name.casefold())
        if len(candidates) > 200:
            notices += ("Résultats limités à 200 ; préciser le filtre.",)
        return RemoteSearch(tuple(candidates[:200]), notices)

    def download(self, candidate: RemoteCandidate) -> RemoteDownload:
        content = self.raw(candidate)
        verify_download(RemoteDownload(candidate, content))
        if candidate.asset_type in (AssetType.SYMBOL, AssetType.FOOTPRINT):
            try:
                root = parse(content.decode("utf-8"))
                check_version(root, candidate.asset_type is AssetType.SYMBOL)
                if candidate.asset_type is AssetType.SYMBOL:
                    if candidate.name not in [
                        n.atoms[1] for n in root.children_named("symbol") if len(n.atoms) == 2
                    ]:
                        raise RemoteError("Symbole absent du fichier téléchargé.")
                elif root.atoms[1:] != [candidate.name]:
                    raise RemoteError("Nom du footprint différent du candidat.")
            except UnicodeError as error:
                raise RemoteError("Fichier KiCad distant non UTF-8.") from error
        return RemoteDownload(candidate, content)
