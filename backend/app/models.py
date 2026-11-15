from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

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
    name_variants: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    tax_id: Mapped[Optional[str]] = mapped_column(String(64))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    mf: Mapped[Optional[str]] = mapped_column(String(20))
    nis: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    aliases: Mapped[List["SupplierAlias"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


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
    reference: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    supplier_ref: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_designation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(128))
    packaging: Mapped[Optional[str]] = mapped_column(String(128))
    stock_unit: Mapped[Optional[str]] = mapped_column(String(32))
    default_vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    aliases: Mapped[List["ProductAlias"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
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
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
    supplier_name_raw: Mapped[Optional[str]] = mapped_column(String(255))
    supplier_code_snapshot: Mapped[Optional[str]] = mapped_column(String(64))
    supplier_match: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    invoice_number: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    document_type: Mapped[Optional[str]] = mapped_column(String(32))
    bl_facture: Mapped[Optional[bool]] = mapped_column(Boolean)
    bc_number: Mapped[Optional[str]] = mapped_column(String(64))
    bc_date: Mapped[Optional[date]] = mapped_column(Date)
    bl_number: Mapped[Optional[str]] = mapped_column(String(64))
    bl_date: Mapped[Optional[date]] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8), default="DZD", nullable=False)

    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    header_raw: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    totals_extracted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    totals_calculated: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checks: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    document_meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    duplicate_reason: Mapped[Optional[str]] = mapped_column(String(255))

    notes: Mapped[Optional[str]] = mapped_column(Text)
    validation_user: Mapped[Optional[str]] = mapped_column(String(128))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    supplier: Mapped[Optional[Supplier]] = relationship()
    pages: Mapped[List["InvoicePage"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoicePage.page_number"
    )
    lines: Mapped[List["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position"
    )
    audits: Mapped[List["AuditEntry"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="AuditEntry.created_at"
    )
    exports: Mapped[List["ExportRecord"]] = relationship(
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
    text: Mapped[Optional[str]] = mapped_column(Text)
    ocr_engine: Mapped[Optional[str]] = mapped_column(String(64))
    rotation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    invoice: Mapped[Invoice] = relationship(back_populates="pages")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_reference: Mapped[Optional[str]] = mapped_column(String(64))
    raw_designation: Mapped[str] = mapped_column(String(255), nullable=False)
    catalog_designation: Mapped[Optional[str]] = mapped_column(String(255))
    tulip_product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    match_status: Mapped[str] = mapped_column(String(32), default="NON_RAPPROCHE", nullable=False)
    match_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    match_candidates: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    lot_number: Mapped[Optional[str]] = mapped_column(String(64))
    packages: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    packaging: Mapped[Optional[str]] = mapped_column(String(64))
    unit_price_ht: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    prix_vente: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    line_total_ht_extracted: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    line_total_ht_calculated: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    discount_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    discount_type: Mapped[Optional[str]] = mapped_column(String(16))

    confidence: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_page: Mapped[Optional[int]] = mapped_column(Integer)
    source_bbox: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    original_values: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    product: Mapped[Optional[Product]] = relationship()


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    invoice: Mapped[Optional[Invoice]] = relationship(back_populates="audits")


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="export_fichier", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="GENERE", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
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
    errors: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
