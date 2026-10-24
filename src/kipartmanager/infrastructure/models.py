"""SQLAlchemy mappings; domain objects remain separate."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )


class NamedRow(Base):
    __abstract__ = True
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class PackageRow(NamedRow):
    __tablename__ = "packages"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_required"),)
    description: Mapped[str] = mapped_column(String, nullable=False)


class PartRow(NamedRow):
    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        CheckConstraint("state IN ('DRAFT', 'IDENTIFIED', 'DEPRECATED')", name="state_valid"),
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    package_id: Mapped[UUID | None] = mapped_column(ForeignKey("packages.id"))


class AssetRow(NamedRow):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        CheckConstraint(
            "asset_type IN ('SYMBOL','FOOTPRINT','MODEL_3D','DATASHEET')", name="type_valid"
        ),
        CheckConstraint(
            "origin IN ('USER_PROVIDED','KICAD_OFFICIAL','MANAGED_LIBRARY',"
            "'MANUFACTURER','TRUSTED_THIRD_PARTY','GENERATED_PARAMETRIC','GENERATED_AI')",
            name="origin_valid",
        ),
        CheckConstraint("validation_state = 'UNCHECKED'", name="validation_unchecked"),
    )
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    provenance_json: Mapped[str | None] = mapped_column(String, nullable=True)
    validation_state: Mapped[str] = mapped_column(String, nullable=False)


class AssetFileRow(Base):
    __tablename__ = "asset_files"
    __table_args__ = (
        CheckConstraint("symbol_name = '' OR extension = '.kicad_sym'", name="symbol_entry"),
        CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="hash_valid"),
        CheckConstraint("typeof(size_bytes) = 'integer' AND size_bytes > 0", name="size_valid"),
        CheckConstraint(
            "extension IN ('.pdf','.step','.stp','.wrl','.kicad_mod','.kicad_sym')",
            name="extension_valid",
        ),
        CheckConstraint(
            "length(original_name) > 0 AND instr(original_name, '/') = 0 "
            "AND instr(original_name, char(92)) = 0 AND original_name NOT IN ('.','..')",
            name="name_valid",
        ),
    )
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extension: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    symbol_name: Mapped[str] = mapped_column(String, nullable=False, default="")


class InventoryRow(NamedRow):
    __tablename__ = "inventories"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
    )


class LocationRow(NamedRow):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
    )


class CollectionRow(NamedRow):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
    )


class StockRow(Base):
    __tablename__ = "stock_items"
    __table_args__ = (
        UniqueConstraint("part_id", "inventory_id"),
        CheckConstraint("typeof(quantity) = 'integer' AND quantity >= 0", name="quantity_valid"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    part_id: Mapped[UUID] = mapped_column(ForeignKey("parts.id"), nullable=False)
    inventory_id: Mapped[UUID] = mapped_column(ForeignKey("inventories.id"), nullable=False)
    location_id: Mapped[UUID | None] = mapped_column(ForeignKey("locations.id"))
    quantity: Mapped[int] = mapped_column(nullable=False)


part_assets = Table(
    "part_assets",
    Base.metadata,
    Column("part_id", Uuid, ForeignKey("parts.id"), primary_key=True),
    Column("asset_id", Uuid, ForeignKey("assets.id"), primary_key=True),
)
package_assets = Table(
    "package_assets",
    Base.metadata,
    Column("package_id", Uuid, ForeignKey("packages.id"), primary_key=True),
    Column("asset_id", Uuid, ForeignKey("assets.id"), primary_key=True),
)
collection_parts = Table(
    "collection_parts",
    Base.metadata,
    Column("collection_id", Uuid, ForeignKey("collections.id"), primary_key=True),
    Column("part_id", Uuid, ForeignKey("parts.id"), primary_key=True),
)


class ChoiceRow(Base):
    __tablename__ = "resource_choices"
    __table_args__ = (
        CheckConstraint("(part_id IS NOT NULL) != (package_id IS NOT NULL)", name="one_owner"),
        CheckConstraint("(asset_id IS NOT NULL) != (reference_json != '')", name="one_resource"),
        CheckConstraint(
            "(part_id IS NOT NULL AND asset_type IN ('SYMBOL','DATASHEET')) OR "
            "(package_id IS NOT NULL AND asset_type IN ('FOOTPRINT','MODEL_3D'))",
            name="role_valid",
        ),
        CheckConstraint(
            "owner_key = CASE WHEN part_id IS NOT NULL THEN 'Part:' || part_id "
            "ELSE 'Package:' || package_id END",
            name="owner_key_valid",
        ),
    )
    owner_key: Mapped[str] = mapped_column(String, primary_key=True)
    asset_type: Mapped[str] = mapped_column(String, primary_key=True)
    part_id: Mapped[UUID | None] = mapped_column(ForeignKey("parts.id"))
    package_id: Mapped[UUID | None] = mapped_column(ForeignKey("packages.id"))
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"))
    reference_json: Mapped[str] = mapped_column(String, nullable=False)


class ValidationRow(Base):
    __tablename__ = "validation_reports"
    __table_args__ = (
        CheckConstraint("(part_id IS NOT NULL) != (collection_id IS NOT NULL)", name="one_subject"),
        CheckConstraint(
            "subject_key = CASE WHEN part_id IS NOT NULL THEN 'Part:' || part_id "
            "ELSE 'Collection:' || collection_id END",
            name="subject_key_valid",
        ),
        CheckConstraint("length(report_json) > 0", name="report_required"),
    )
    subject_key: Mapped[str] = mapped_column(String, primary_key=True)
    part_id: Mapped[UUID | None] = mapped_column(ForeignKey("parts.id"))
    collection_id: Mapped[UUID | None] = mapped_column(ForeignKey("collections.id"))
    report_json: Mapped[str] = mapped_column(String, nullable=False)


class IdentificationRow(Base):
    __tablename__ = "part_identifications"
    __table_args__ = (
        CheckConstraint("typeof(revision) = 'integer' AND revision > 0", name="revision_valid"),
        CheckConstraint("length(data_json) > 0", name="data_required"),
    )
    part_id: Mapped[UUID] = mapped_column(ForeignKey("parts.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    data_json: Mapped[str] = mapped_column(String, nullable=False)


class DocumentRow(Base):
    __tablename__ = "part_documents"
    __table_args__ = (
        UniqueConstraint("part_id", "asset_id"),
        CheckConstraint("length(data_json) > 0", name="data_required"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    part_id: Mapped[UUID] = mapped_column(ForeignKey("parts.id"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    data_json: Mapped[str] = mapped_column(String, nullable=False)
