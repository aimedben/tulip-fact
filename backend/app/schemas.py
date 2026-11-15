from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentType = Literal["FACTURE", "BL", "AVOIR", "AUTRE"]


class TotalsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_ht: Decimal | None = None
    discount_total: Decimal | None = None
    vat_total: Decimal | None = None
    vat_breakdown: dict[str, Decimal] | None = None
    other_taxes: Decimal | None = None
    timbre: Decimal | None = None
    total_ttc: Decimal | None = None


class InvoiceHeaderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_date: date | None = None
    invoice_number: str | None = Field(default=None, max_length=64)
    document_type: DocumentType | None = None
    bl_facture: bool | None = None
    bc_number: str | None = Field(default=None, max_length=64)
    bc_date: date | None = None
    bl_number: str | None = Field(default=None, max_length=64)
    bl_date: date | None = None
    currency: str | None = Field(default=None, max_length=8)
    supplier_name_raw: str | None = Field(default=None, max_length=255)
    totals: TotalsIn | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_reference: str | None = Field(default=None, max_length=64)
    raw_designation: str | None = Field(default=None, max_length=255)
    lot_number: str | None = Field(default=None, max_length=64)
    packages: Decimal | None = Field(default=None, ge=0)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    packaging: str | None = Field(default=None, max_length=64)
    unit_price_ht: Decimal | None = Field(default=None, ge=0)
    prix_vente: Decimal | None = Field(default=None, ge=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    line_total_ht_extracted: Decimal | None = None
    discount_value: Decimal | None = Field(default=None, ge=0)
    discount_type: Literal["percent", "value"] | None = None


class LineCreate(LineUpdate):
    raw_designation: str = Field(min_length=1, max_length=255)
    position: int | None = None


class SupplierConfirm(BaseModel):
    supplier_id: int
    supplier_name_raw: str | None = Field(default=None, max_length=255)


class ProductConfirm(BaseModel):
    product_id: int


class NewProductFromLine(BaseModel):
    designation: str | None = Field(default=None, max_length=255)
    tulip_code: str | None = Field(default=None, max_length=64)
    reference: str | None = Field(default=None, max_length=64)
    supplier_ref: str | None = Field(default=None, max_length=64)
    packaging: str | None = Field(default=None, max_length=128)
    stock_unit: str | None = Field(default=None, max_length=32)
    default_vat_rate: Decimal | None = Field(default=None, ge=0, le=100)


class ValidateRequest(BaseModel):
    actor: str = Field(default="Administrateur", max_length=128)
    acknowledge_duplicate: bool = False
    acknowledge_totals: bool = False
    acknowledge_warnings: bool = False


class ExportRequest(BaseModel):
    formats: list[Literal["csv", "xlsx", "json", "rapport"]] = Field(
        default_factory=lambda: ["csv", "xlsx", "json", "rapport"]
    )
    actor: str = Field(default="Administrateur", max_length=128)


class SupplierCreate(BaseModel):
    # Vide = code Tulip choisi automatiquement (PRINCIPAL suivant).
    code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    name_variants: list[str] = Field(default_factory=list)
    tax_id: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    mf: str | None = Field(default=None, max_length=20)
    nis: str | None = Field(default=None, max_length=20)
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    name_variants: list[str] | None = None
    tax_id: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    mf: str | None = Field(default=None, max_length=20)
    nis: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    active: bool | None = None


class ProductCreate(BaseModel):
    # Vide = code article Tulip choisi automatiquement (CODE suivant).
    tulip_code: str | None = Field(default=None, max_length=64)
    designation: str = Field(min_length=1, max_length=255)
    reference: str | None = Field(default=None, max_length=64)
    supplier_ref: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=128)
    packaging: str | None = Field(default=None, max_length=128)
    stock_unit: str | None = Field(default=None, max_length=32)
    default_vat_rate: Decimal | None = Field(default=None, ge=0, le=100)


class ProductUpdate(BaseModel):
    designation: str | None = Field(default=None, min_length=1, max_length=255)
    reference: str | None = Field(default=None, max_length=64)
    supplier_ref: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=128)
    packaging: str | None = Field(default=None, max_length=128)
    stock_unit: str | None = Field(default=None, max_length=32)
    default_vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    active: bool | None = None


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    keep_image: bool = False
