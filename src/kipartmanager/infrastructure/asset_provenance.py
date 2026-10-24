"""SQLite JSON representation of portable provenance; no credentials are accepted."""

import json
from dataclasses import asdict

from kipartmanager.domain.asset_provenance import AssetProvenance, Redistribution
from kipartmanager.domain.entities import DomainError


def encode_provenance(value: AssetProvenance | None) -> str | None:
    return json.dumps(asdict(value), ensure_ascii=False, sort_keys=True) if value else None


def decode_provenance(raw: str | None) -> AssetProvenance | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        data["redistribution"] = Redistribution(data["redistribution"])
        return AssetProvenance(**data)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise DomainError("Provenance d’asset illisible ; fichier conservé.") from error
