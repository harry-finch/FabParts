"""Local draft ingestion, using existing domain services inside one transaction."""

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from kipartmanager.application.asset_imports import AssetImports
from kipartmanager.application.asset_previews import AssetPreviews
from kipartmanager.application.catalogue import Catalogue
from kipartmanager.application.discovery import LocalDiscovery
from kipartmanager.application.kicad import KiCadLibraries
from kipartmanager.application.resolver import LocalResolver
from kipartmanager.domain.documentation import (
    FieldValue,
    MetadataField,
    MetadataProposal,
    MetadataSource,
)
from kipartmanager.domain.entities import (
    Asset,
    AssetOrigin,
    AssetType,
    Collection,
    ConflictError,
    DomainError,
    Package,
    Part,
    PartState,
)
from kipartmanager.domain.resolution import Candidate, CandidateTier, ResourceChoice
from kipartmanager.ports.asset_store import AssetStore
from kipartmanager.ports.discovery import DiscoveryProbe
from kipartmanager.ports.documentation import DocumentationRepository
from kipartmanager.ports.ingestion import IngestionTransaction, IngestionTransactions, Receipt
from kipartmanager.ports.prepared_files import PreparedFile, PreparedFiles


def normalized(value: str) -> str:
    # No fuzzy identity or punctuation removal: different vendor references stay distinct.
    return " ".join(value.split()).casefold()


@dataclass(frozen=True)
class IngestionFields:
    reference: str = ""
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    category: str = ""
    package_id: str = ""
    package_name: str = ""
    collections: tuple[str, ...] = ()

    def validate(self) -> None:
        for key in ("reference", "mpn", "manufacturer", "description", "category", "package_name"):
            value = getattr(self, key)
            if not isinstance(value, str) or len(value) > 2048 or "\x00" in value:
                raise DomainError("Texte invalide ou trop long.")
        if not (self.reference.strip() or self.mpn.strip()):
            raise DomainError("Saisir une référence ou un MPN avant l’enregistrement.")
        if self.package_id and self.package_name.strip():
            raise DomainError("Choisir un package existant ou nommer un nouveau package.")
        if (
            not self.collections
            or len(self.collections) > 32
            or len(set(self.collections)) != len(self.collections)
        ):
            raise DomainError("Choisir au moins une bibliothèque distincte.")
        try:
            for identity in (*self.collections, *((self.package_id,) if self.package_id else ())):
                UUID(identity)
        except (ValueError, TypeError) as error:
            raise DomainError("Identifiant de bibliothèque ou de package invalide.") from error


@dataclass(frozen=True)
class PendingCandidate:
    token: str
    role: AssetType
    name: str
    prepared: PreparedFile | None = None
    symbol: str = ""
    candidate: Candidate | None = None

    def dto(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "role": self.role.value,
            "name": self.name,
            "origin": self.candidate.origin if self.candidate else "USER_PROVIDED",
            "storage": "staged"
            if self.prepared
            else "managed"
            if self.candidate and self.candidate.asset
            else "reference",
            "sha256": self.prepared.file.sha256
            if self.prepared
            else self.candidate.sha256
            if self.candidate
            else "",
            "warning": self.candidate.unavailable if self.candidate else "",
            "validation_state": "UNCHECKED",
        }


@dataclass
class IngestionPreparation:
    handle: str
    operation_id: UUID
    part: Part | None
    snapshot: str
    candidates: dict[str, PendingCandidate] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    pdf_handles: list[str] = field(default_factory=list)
    model_handles: list[str] = field(default_factory=list)
    metadata: dict[str, MetadataProposal] = field(default_factory=dict)
    discovered: dict[str, list[Candidate]] = field(default_factory=dict)
    discovery_fields: IngestionFields | None = None


class Ingestion:
    def __init__(
        self,
        catalogue: Catalogue,
        documentation: DocumentationRepository,
        resolver: LocalResolver,
        transactions: IngestionTransactions,
        store: AssetStore,
        files: PreparedFiles,
        previews: AssetPreviews,
        libraries: KiCadLibraries | None = None,
        probe: DiscoveryProbe | None = None,
    ) -> None:
        self.catalogue, self.documentation, self.resolver = catalogue, documentation, resolver
        self.transactions, self.store, self.files = transactions, store, files
        self.previews, self.libraries = previews, libraries
        self.discovery = LocalDiscovery(catalogue, documentation, resolver, probe)
        self.preparation: IngestionPreparation | None = None

    @staticmethod
    def _snapshot(cat: Catalogue, doc: DocumentationRepository, part: Part) -> str:
        package = cat.require(Package, part.package_id) if part.package_id else None
        return json.dumps(
            {
                "part": asdict(part),
                "collections": sorted(
                    str(c.id) for c in cat.list_entities(Collection) if part.id in c.part_ids
                ),
                "identification": asdict(doc.identification(part.id)),
                "choices": [asdict(c) for c in cat.repository.choices(part)],
                "package": asdict(package) if package else None,
                "package_choices": [asdict(c) for c in cat.repository.choices(package)]
                if package
                else [],
            },
            sort_keys=True,
            default=str,
        )

    def _preparation(self, handle: str) -> IngestionPreparation:
        if self.preparation is None or self.preparation.handle != handle:
            raise DomainError("Préparation absente ; recommencer l’ajout.")
        self.files.files(handle)  # Enforce expiry even for an empty preparation.
        return self.preparation

    def _candidate(
        self, prep: IngestionPreparation, key: str, value: PendingCandidate
    ) -> PendingCandidate:
        if key in prep.keys:
            return prep.candidates[prep.keys[key]]
        if len(prep.candidates) >= 256:
            raise DomainError("Trop de candidats ; recommencer avec une recherche plus précise.")
        prep.keys[key] = value.token
        prep.candidates[value.token] = value
        return value

    def _existing_candidate(
        self, prep: IngestionPreparation, choice: ResourceChoice
    ) -> PendingCandidate:
        asset = self.catalogue.require(Asset, choice.asset_id) if choice.asset_id else None
        candidate = Candidate(
            CandidateTier.MANAGED if asset else CandidateTier.KICAD,
            choice,
            asset.name if asset else choice.reference.identifier if choice.reference else "",
            asset,
        )
        return self._candidate(
            prep,
            choice.key,
            PendingCandidate(
                secrets.token_hex(24),
                choice.asset_type,
                candidate.name,
                candidate=candidate,
            ),
        )

    def begin(self, part_id: str = "") -> dict[str, Any]:
        part = self.catalogue.require(Part, UUID(part_id)) if part_id else None
        if part and part.state is not PartState.DRAFT:
            raise DomainError("Seuls les brouillons peuvent être complétés par cet assistant.")
        if self.preparation:
            self.cancel(self.preparation.handle)
        handle = self.files.begin()
        prep = IngestionPreparation(
            handle,
            uuid4(),
            part,
            self._snapshot(self.catalogue, self.documentation, part) if part else "",
        )
        self.preparation = prep
        fields = IngestionFields()
        selections: dict[str, str] = {}
        if part:
            identity = self.documentation.identification(part.id)
            fields = IngestionFields(
                reference=part.name,
                mpn=identity.value(MetadataField.MPN),
                manufacturer=identity.value(MetadataField.MANUFACTURER),
                description=part.description,
                category=identity.value(MetadataField.CATEGORY),
                package_id=str(part.package_id) if part.package_id else "",
                collections=tuple(
                    str(c.id)
                    for c in self.catalogue.list_entities(Collection)
                    if part.id in c.part_ids
                ),
            )
            owners: list[Part | Package] = [part]
            if part.package_id:
                owners.append(self.catalogue.require(Package, part.package_id))
            for owner in owners:
                for choice in self.catalogue.repository.choices(owner):
                    selections[choice.asset_type.value] = self._existing_candidate(
                        prep, choice
                    ).token
        return {
            "preparation": handle,
            "operation_id": str(prep.operation_id),
            "part_id": str(part.id) if part else "",
            "fields": asdict(fields),
            "selections": selections,
            "candidates": [c.dto() for c in prep.candidates.values()],
            "collections": [
                {"id": str(c.id), "name": c.name} for c in self.catalogue.list_entities(Collection)
            ],
            "packages": [
                {"id": str(p.id), "name": p.name} for p in self.catalogue.list_entities(Package)
            ],
            "categories": sorted(
                {
                    self.documentation.identification(p.id).value(MetadataField.CATEGORY)
                    for p in self.catalogue.list_entities(Part)
                }
                - {""}
            ),
        }

    def search(self, preparation: str, role: str, query: str = "") -> dict[str, Any]:
        prep = self._preparation(preparation)
        kind = AssetType(role)
        values: list[PendingCandidate] = []
        for staged in self.files.files(preparation):
            if staged.file.asset_type != kind:
                continue
            for symbol in staged.symbols or ("",):
                values.append(
                    self._candidate(
                        prep,
                        staged.handle + ":" + symbol,
                        PendingCandidate(
                            secrets.token_hex(24),
                            kind,
                            symbol or staged.file.original_name,
                            staged,
                            symbol,
                        ),
                    )
                )
        result = self.resolver.search_candidates(kind, query)
        for candidate in result.candidates[:40]:
            values.append(
                self._candidate(
                    prep,
                    candidate.choice.key,
                    PendingCandidate(
                        secrets.token_hex(24),
                        kind,
                        candidate.name,
                        candidate=candidate,
                    ),
                )
            )
        return {"candidates": [c.dto() for c in values], "notices": result.notices}

    def discover(self, preparation: str, fields: IngestionFields, role: str) -> dict[str, Any]:
        prep = self._preparation(preparation)
        if not (fields.reference.strip() or fields.mpn.strip()):
            raise DomainError("Saisir une référence ou un MPN pour rechercher.")
        if role == "SYMBOL":
            prep.discovered = {}
            prep.discovery_fields = fields
        elif prep.discovery_fields != fields:
            raise ConflictError("Identification modifiée ; relancer la recherche guidée.")
        suggestions, parts, notices = self.discovery.search(
            AssetType(role), fields.reference, fields.mpn, fields.package_name, prep.discovered
        )
        prep.discovered[role] = [s.candidate for s in suggestions]
        # Supplied files remain visible alongside suggestions, never silently replaced.
        supplied = self.search(preparation, role, fields.mpn or fields.reference)
        values = {c["token"]: c for c in supplied["candidates"] if c["storage"] == "staged"}
        for suggestion in suggestions:
            candidate = suggestion.candidate
            pending = self._candidate(
                prep,
                candidate.choice.key,
                PendingCandidate(
                    secrets.token_hex(24),
                    AssetType(role),
                    candidate.name,
                    candidate=candidate,
                ),
            )
            values[pending.token] = {
                **pending.dto(),
                "match": suggestion.match,
                "reason": suggestion.reason,
                "source": suggestion.source,
                "package": suggestion.package,
            }
        metadata = []
        packages = {}
        for part in parts:
            identity = self.documentation.identification(part.id)
            source = MetadataSource(
                ("Catalogue FabParts · " + part.name)[:2048],
                f"fabparts:part:{part.id}:identification:{identity.revision}",
            )
            for item in identity.values:
                if item.field not in {
                    MetadataField.MPN,
                    MetadataField.MANUFACTURER,
                    MetadataField.CATEGORY,
                }:
                    continue
                if not item.value.strip() or len(item.value) > 2048:
                    continue
                proposal = MetadataProposal(source, (FieldValue(item.field, item.value.strip()),))
                token = next((k for k, v in prep.metadata.items() if v == proposal), "")
                if not token:
                    if len(prep.metadata) >= 128:
                        raise DomainError("Trop de propositions ; recommencer l’ajout.")
                    token = secrets.token_hex(24)
                    prep.metadata[token] = proposal
                metadata.append(
                    {
                        "token": token,
                        "field": item.field.value,
                        "value": item.value.strip(),
                        "source": source.label,
                        "reference": source.reference,
                    }
                )
            if part.package_id:
                package = self.catalogue.require(Package, part.package_id)
                packages[str(package.id)] = {
                    "id": str(package.id),
                    "name": package.name,
                    "source": part.name,
                }
        return {
            "candidates": list(values.values()),
            "metadata": metadata,
            "packages": list(packages.values()),
            "similar": [{"id": str(p.id), "name": p.name} for p in parts],
            "notices": list(dict.fromkeys(notices)),
            "role": role,
        }

    def duplicates(
        self,
        fields: IngestionFields,
        cat: Catalogue | None = None,
        doc: DocumentationRepository | None = None,
        exclude: UUID | None = None,
    ) -> list[dict[str, str]]:
        cat, doc = cat or self.catalogue, doc or self.documentation
        result = []
        for part in cat.list_entities(Part):
            if part.id == exclude:
                continue
            identity = doc.identification(part.id)
            mpn, maker = (
                identity.value(MetadataField.MPN),
                identity.value(MetadataField.MANUFACTURER),
            )
            reference_match = normalized(part.name) == normalized(
                fields.reference.strip() or fields.mpn.strip()
            )
            mpn_match = bool(
                fields.mpn.strip() and mpn.strip() and normalized(mpn) == normalized(fields.mpn)
            )
            different_maker = bool(
                maker
                and fields.manufacturer
                and normalized(maker) != normalized(fields.manufacturer)
            )
            if reference_match or (mpn_match and not different_maker):
                result.append(
                    {"id": str(part.id), "name": part.name, "mpn": mpn, "manufacturer": maker}
                )
        return result

    def inspect(self, preparation: str, fields: IngestionFields) -> dict[str, Any]:
        prep = self._preparation(preparation)
        selections = {}
        if fields.package_id:
            package = self.catalogue.require(Package, UUID(fields.package_id))
            selections = {
                c.asset_type.value: self._existing_candidate(prep, c).token
                for c in self.catalogue.repository.choices(package)
            }
        return {
            "duplicates": self.duplicates(fields, exclude=prep.part.id if prep.part else None),
            "package_selections": selections,
            "candidates": [c.dto() for c in prep.candidates.values()],
        }

    def preview(self, preparation: str, token: str) -> dict[str, Any]:
        prep = self._preparation(preparation)
        pending = prep.candidates.get(token)
        if pending is None:
            raise DomainError("Candidat non autorisé pour cette préparation.")
        metadata = pending.dto()
        if pending.prepared:
            content = self.files.preview(preparation, pending.prepared.handle, pending.symbol)
            source = pending.prepared.file.original_name
        else:
            assert pending.candidate is not None
            preview = self.previews.previews.inspect(pending.candidate.choice)
            content, source = preview.content, preview.source
        result = self.previews.present(
            pending.role,
            content,
            {
                "status": "ready",
                "kind": pending.role.value,
                "selected": False,
                "name": pending.name,
                "origin": metadata["origin"],
                "source": source,
                "sha256": metadata["sha256"],
                "storage": metadata["storage"],
            },
        )
        if "handle" in result:
            handles = prep.model_handles if pending.role is AssetType.MODEL_3D else prep.pdf_handles
            handles[:] = [*handles[-1:], result["handle"]]
        return result

    def remove(self, preparation: str, handle: str) -> dict[str, Any]:
        prep = self._preparation(preparation)
        self.files.discard(preparation, handle)
        removed = [
            token
            for token, candidate in prep.candidates.items()
            if candidate.prepared and candidate.prepared.handle == handle
        ]
        prep.candidates = {k: v for k, v in prep.candidates.items() if k not in removed}
        prep.keys = {k: v for k, v in prep.keys.items() if v not in removed}
        return {"removed": removed}

    def commit(
        self,
        preparation: str,
        operation_id: str,
        fields: IngestionFields,
        selections: dict[str, str],
        action: str = "save",
        existing_id: str = "",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, str]:
        fields.validate()
        if action not in {"save", "variant", "membership"}:
            raise DomainError("Action de confirmation inconnue.")
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "fields": asdict(fields),
                    "selections": selections,
                    "action": action,
                    "existing_id": existing_id,
                    "preparation": preparation,
                    **({"metadata": metadata} if metadata else {}),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        operation = UUID(operation_id)
        with self.transactions.begin() as transaction:
            receipt = transaction.receipt(operation)
            if receipt:
                if receipt.request_sha256 != request_hash:
                    raise ConflictError("Cette confirmation correspond à une autre requête.")
                return {
                    "status": "saved",
                    "part_id": str(receipt.part_id),
                    "operation_id": operation_id,
                }
            prep = self._preparation(preparation)
            if prep.operation_id != operation:
                raise DomainError("Opération non autorisée dans cette préparation.")
            cat = Catalogue(transaction.catalogue, self.store)
            doc = transaction.documentation
            # Validate every selected role/capability before publishing even one blob.
            pending = []
            for role, token in selections.items():
                candidate = prep.candidates.get(token)
                if candidate is None or candidate.role.value != role:
                    raise DomainError("Choix de ressource invalide ou hors préparation.")
                pending.append(candidate)
            if prep.part:
                current = cat.require(Part, prep.part.id)
                if self._snapshot(cat, doc, current) != prep.snapshot:
                    raise ConflictError("Le brouillon a changé ; le rouvrir avant d’enregistrer.")
            duplicates = self.duplicates(fields, cat, doc, prep.part.id if prep.part else None)
            if action == "membership":
                if existing_id not in {d["id"] for d in duplicates}:
                    raise ConflictError("Le composant existant ne correspond plus à la référence.")
                part = cat.require(Part, UUID(existing_id))
            else:
                if duplicates and action != "variant":
                    raise ConflictError(
                        "Doublon détecté : choisir l’existant ou confirmer une variante."
                    )
                if action == "variant" and (
                    prep.part
                    or not duplicates
                    or any(
                        normalized(d["name"])
                        == normalized(fields.reference.strip() or fields.mpn.strip())
                        for d in duplicates
                    )
                ):
                    raise DomainError("Une variante nécessite une référence distincte explicite.")
                part = self._save(prep, fields, pending, transaction, cat, metadata or {})
            for collection_id in fields.collections:
                collection = cat.require(Collection, UUID(collection_id))
                cat.save(
                    replace(
                        collection, part_ids=tuple(sorted(set((*collection.part_ids, part.id))))
                    )
                )
            if prep.part and action != "membership":
                for collection in cat.list_entities(Collection):
                    if (
                        part.id in collection.part_ids
                        and str(collection.id) not in fields.collections
                    ):
                        cat.save(
                            replace(
                                collection,
                                part_ids=tuple(p for p in collection.part_ids if p != part.id),
                            )
                        )
            transaction.record(Receipt(operation, request_hash, part.id))
        # Failure to remove temporary files must never hide a successful durable commit.
        try:
            self.cancel(preparation)
        except OSError:
            pass
        return {"status": "saved", "part_id": str(part.id), "operation_id": operation_id}

    def _save(
        self,
        prep: IngestionPreparation,
        fields: IngestionFields,
        pending: list[PendingCandidate],
        transaction: IngestionTransaction,
        cat: Catalogue,
        metadata: dict[str, str],
    ) -> Part:
        for key, token in metadata.items():
            proposal = prep.metadata.get(token)
            if (
                proposal is None
                or key not in {"mpn", "manufacturer", "category"}
                or proposal.values[0].field.value != key
                or proposal.values[0].value != getattr(fields, key).strip()
            ):
                raise ConflictError("Proposition modifiée ou hors préparation ; la relire.")
        package = cat.require(Package, UUID(fields.package_id)) if fields.package_id else None
        if fields.package_name.strip():
            if any(
                normalized(p.name) == normalized(fields.package_name)
                for p in cat.list_entities(Package)
            ):
                raise ConflictError(
                    "Ce nom de package existe ; sélectionner le package ou nommer une variante."
                )
            package = Package(name=fields.package_name.strip())
            cat.save(package)
        mechanical = [p for p in pending if p.role in {AssetType.FOOTPRINT, AssetType.MODEL_3D}]
        if mechanical and package is None:
            raise DomainError("Choisir ou nommer un package pour les ressources mécaniques.")
        if fields.package_id and package:
            choices = {c.asset_type: c for c in transaction.catalogue.choices(package)}
            for selection in mechanical:
                if (
                    selection.candidate is None
                    or choices.get(selection.role) != selection.candidate.choice
                ):
                    raise ConflictError(
                        "Le package partagé est conservé ; créer un package distinct "
                        "pour changer ses ressources."
                    )
        part = replace(
            prep.part or Part(name=fields.reference.strip() or fields.mpn.strip()),
            name=fields.reference.strip() or fields.mpn.strip(),
            description=fields.description.strip(),
            package_id=package.id if package else None,
        )
        if prep.part and any(
            choice.asset_type not in {selection.role for selection in pending}
            for choice in transaction.catalogue.choices(prep.part)
        ):
            raise DomainError("Pour remplacer une ressource existante, choisir sa remplaçante.")
        cat.save(part)
        imports = AssetImports(cat, self.store)
        resolver = LocalResolver(cat, transaction.catalogue, self.libraries)
        for selection in pending:
            owner = part if selection.role in {AssetType.SYMBOL, AssetType.DATASHEET} else package
            assert owner is not None
            if owner is package and fields.package_id:
                continue
            candidate = selection.candidate
            if selection.prepared:
                staged = selection.prepared
                if staged.symbols and selection.symbol not in staged.symbols:
                    raise DomainError(
                        "Choisir une entrée explicite dans la bibliothèque de symboles."
                    )
                asset = imports.import_content(
                    self.files.content(prep.handle, staged.handle),
                    staged.file.original_name,
                    name=selection.name,
                    origin=AssetOrigin.USER_PROVIDED,
                    source_reference=staged.file.original_name,
                    symbol_name=selection.symbol,
                )
                candidate = Candidate(
                    CandidateTier.USER, ResourceChoice(selection.role, asset.id), asset.name, asset
                )
            assert candidate is not None
            current = next(
                (c for c in resolver.choices(owner) if c.asset_type == selection.role), None
            )
            resolver.select(owner, candidate, expected=current, replace_existing=True)
        identity = transaction.documentation.identification(part.id)
        values = tuple(
            FieldValue(f, v.strip())
            for f, v in (
                (MetadataField.MPN, fields.mpn),
                (MetadataField.MANUFACTURER, fields.manufacturer),
                (MetadataField.CATEGORY, fields.category),
            )
            if identity.value(f) != v.strip()
        )
        manual = tuple(v for v in values if v.field.value not in metadata)
        proposals = (
            [
                MetadataProposal(
                    MetadataSource("Saisie utilisateur", "FabParts local ingestion"), manual
                )
            ]
            if manual
            else []
        ) + [prep.metadata[metadata[v.field.value]] for v in values if v.field.value in metadata]
        for proposal in proposals:
            updated = identity.accept(
                proposal,
                tuple(v.field for v in proposal.values),
                replace_existing=True,
                recorded_at=datetime.now(UTC).isoformat(),
            )
            transaction.documentation.save_identification(updated, identity)
            identity = updated

        return cat.require(Part, part.id)

    def result(self, operation_id: str) -> dict[str, str]:
        receipt = self.transactions.receipt(UUID(operation_id))
        return (
            {"status": "saved", "part_id": str(receipt.part_id), "operation_id": operation_id}
            if receipt
            else {"status": "not_committed", "operation_id": operation_id}
        )

    def cancel(self, preparation: str) -> dict[str, bool]:
        if self.preparation and self.preparation.handle == preparation:
            for handle in self.preparation.pdf_handles:
                self.previews.release(handle)
            if self.previews.models:
                for handle in self.preparation.model_handles:
                    self.previews.models.release(handle)
        self.files.cancel(preparation)
        if self.preparation and self.preparation.handle == preparation:
            self.preparation = None
        return {"cancelled": True}

    def close(self) -> None:
        if self.preparation:
            self.cancel(self.preparation.handle)
        self.files.close()
        self.preparation = None
