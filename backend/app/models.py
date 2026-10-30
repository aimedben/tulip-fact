from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name_variants: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    aliases: Mapped[list["SupplierAlias"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class SupplierAlias(Base):
    __tablename__ = "supplier_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="confirmation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    supplier: Mapped[Supplier] = relationship(back_populates="aliases")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tulip_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    supplier_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    barcode: Mapped[str | None] = mapped_column(String(64), index=True)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(128))
    packaging: Mapped[str | None] = mapped_column(String(128))
    stock_unit: Mapped[str | None] = mapped_column(String(32))
    default_vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    aliases: Mapped[list["ProductAlias"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
    raw_designation: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="confirmation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    product: Mapped[Product] = relationship(back_populates="aliases")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="IMPORTEE", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), default="import", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
    supplier_name_raw: Mapped[str | None] = mapped_column(String(255))
    supplier_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    supplier_match: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    invoice_number: Mapped[str | None] = mapped_column(String(64), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    document_type: Mapped[str | None] = mapped_column(String(32))
    bl_facture: Mapped[bool | None] = mapped_column(Boolean)
    bc_number: Mapped[str | None] = mapped_column(String(64))
    bc_date: Mapped[date | None] = mapped_column(Date)
    bl_number: Mapped[str | None] = mapped_column(String(64))
    bl_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8), default="DZD", nullable=False)

    raw_text: Mapped[str | None] = mapped_column(Text)
    header_raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    totals_extracted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    totals_calculated: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    document_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    duplicate_reason: Mapped[str | None] = mapped_column(String(255))

    notes: Mapped[str | None] = mapped_column(Text)
    validation_user: Mapped[str | None] = mapped_column(String(128))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    supplier: Mapped[Supplier | None] = relationship()
    pages: Mapped[list["InvoicePage"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoicePage.page_number"
    )
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position"
    )
    audits: Mapped[list["AuditEntry"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="AuditEntry.created_at"
    )
    exports: Mapped[list["ExportRecord"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="ExportRecord.created_at"
    )

    __table_args__ = (
        Index("ix_invoices_supplier_number", "supplier_id", "invoice_number"),
        Index("ix_invoices_status_date", "status", "invoice_date"),
    )


class InvoicePage(Base):
    __tablename__ = "invoice_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    ocr_engine: Mapped[str | None] = mapped_column(String(64))
    rotation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    invoice: Mapped[Invoice] = relationship(back_populates="pages")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_reference: Mapped[str | None] = mapped_column(String(64))
    raw_designation: Mapped[str] = mapped_column(String(255), nullable=False)
    catalog_designation: Mapped[str | None] = mapped_column(String(255))
    tulip_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    match_status: Mapped[str] = mapped_column(String(32), default="NON_RAPPROCHE", nullable=False)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    match_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    lot_number: Mapped[str | None] = mapped_column(String(64))
    packages: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(32))
    packaging: Mapped[str | None] = mapped_column(String(64))
    unit_price_ht: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    line_total_ht_extracted: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    line_total_ht_calculated: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_type: Mapped[str | None] = mapped_column(String(16))

    confidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    original_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    invoice: Mapped[Invoice | None] = relationship(back_populates="audits")


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="export_fichier", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="GENERE", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="exports")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
