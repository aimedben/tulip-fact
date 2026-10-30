from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..models import AuditEntry, ExportRecord, Invoice, InvoiceLine, InvoicePage, Product, Supplier
from ..normalization import to_jsonable


def num(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def supplier_payload(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "name_variants": supplier.name_variants or [],
        "tax_id": supplier.tax_id,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
        "notes": supplier.notes,
        "active": supplier.active,
    }


def product_payload(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "tulip_code": product.tulip_code,
        "supplier_ref": product.supplier_ref,
        "barcode": product.barcode,
        "designation": product.designation,
        "brand": product.brand,
        "packaging": product.packaging,
        "stock_unit": product.stock_unit,
        "default_vat_rate": num(product.default_vat_rate),
        "active": product.active,
    }


def page_payload(page: InvoicePage) -> dict[str, Any]:
    return {
        "id": page.id,
        "page_number": page.page_number,
        "image_url": f"/api/invoices/{page.invoice_id}/pages/{page.page_number}/image",
        "ocr_engine": page.ocr_engine,
        "rotation": page.rotation,
        "width": page.width,
        "height": page.height,
        "confidence": num(page.confidence),
    }


def line_payload(line: InvoiceLine) -> dict[str, Any]:
    product = line.product
    return {
        "id": line.id,
        "position": line.position,
        "raw_reference": line.raw_reference,
        "raw_designation": line.raw_designation,
        "catalog_designation": line.catalog_designation,
        "tulip_product_id": line.tulip_product_id,
        "tulip_product": product_payload(product) if product else None,
        "match_status": line.match_status,
        "match_score": num(line.match_score),
        "match_candidates": line.match_candidates or [],
        "lot_number": line.lot_number,
        "packages": num(line.packages),
        "quantity": num(line.quantity),
        "unit": line.unit,
        "packaging": line.packaging,
        "unit_price_ht": num(line.unit_price_ht),
        "vat_rate": num(line.vat_rate),
        "line_total_ht_extracted": num(line.line_total_ht_extracted),
        "line_total_ht_calculated": num(line.line_total_ht_calculated),
        "discount_value": num(line.discount_value),
        "discount_type": line.discount_type,
        "confidence": line.confidence or {},
        "source_page": line.source_page,
        "source_bbox": line.source_bbox,
        "original_values": line.original_values or {},
        "user_modified": line.user_modified,
    }


def invoice_summary(invoice: Invoice) -> dict[str, Any]:
    supplier = invoice.supplier
    return {
        "id": invoice.id,
        "uuid": invoice.uuid,
        "original_filename": invoice.original_filename,
        "status": invoice.status,
        "stage": invoice.stage,
        "progress": invoice.progress,
        "invoice_number": invoice.invoice_number,
        "invoice_date": iso(invoice.invoice_date),
        "supplier_id": invoice.supplier_id,
        "supplier_code": invoice.supplier_code_snapshot or (supplier.code if supplier else None),
        "supplier_name": supplier.name if supplier else invoice.supplier_name_raw,
        "total_ttc": num(Decimal(str((invoice.totals_extracted or {}).get("total_ttc")))
                         if (invoice.totals_extracted or {}).get("total_ttc") not in (None, "") else None),
        "currency": invoice.currency,
        "is_duplicate": invoice.is_duplicate,
        "page_count": invoice.page_count,
        "imported_at": iso(invoice.imported_at),
        "processed_at": iso(invoice.processed_at),
        "validated_at": iso(invoice.validated_at),
        "exported_at": iso(invoice.exported_at),
        "error_message": invoice.error_message,
        "lines_count": len(invoice.lines),
    }


def audit_payload(entry: AuditEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "action": entry.action,
        "actor": entry.actor,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "details": entry.details or {},
        "created_at": iso(entry.created_at),
    }


def export_payload(record: ExportRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "invoice_id": record.invoice_id,
        "format": record.format,
        "mode": record.mode,
        "status": record.status,
        "note": record.note,
        "created_at": iso(record.created_at),
        "download_url": f"/api/exports/{record.id}/download",
        "sha256": record.sha256,
    }


def invoice_detail(invoice: Invoice, readiness: dict[str, Any]) -> dict[str, Any]:
    payload = invoice_summary(invoice)
    payload.update(
        {
            "sha256": invoice.sha256,
            "mime_type": invoice.mime_type,
            "file_size": invoice.file_size,
            "document_type": invoice.document_type,
            "bl_facture": invoice.bl_facture,
            "bc_number": invoice.bc_number,
            "bc_date": iso(invoice.bc_date),
            "bl_number": invoice.bl_number,
            "bl_date": iso(invoice.bl_date),
            "notes": invoice.notes,
            "validation_user": invoice.validation_user,
            "supplier_name_raw": invoice.supplier_name_raw,
            "supplier": supplier_payload(invoice.supplier) if invoice.supplier else None,
            "supplier_match": invoice.supplier_match or {},
            "header_raw": invoice.header_raw or {},
            "totals_extracted": invoice.totals_extracted or {},
            "totals_calculated": invoice.totals_calculated or {},
            "checks": invoice.checks or [],
            "warnings": invoice.warnings or [],
            "document_meta": invoice.document_meta or {},
            "duplicate_reason": invoice.duplicate_reason,
            "duplicate_of_id": invoice.duplicate_of_id,
            "pages": [page_payload(page) for page in invoice.pages],
            "lines": [line_payload(line) for line in invoice.lines],
            "audits": [audit_payload(entry) for entry in invoice.audits],
            "exports": [export_payload(record) for record in invoice.exports],
            "readiness": readiness,
        }
    )
    return payload


def as_jsonable(value: Any) -> Any:
    return to_jsonable(value)
