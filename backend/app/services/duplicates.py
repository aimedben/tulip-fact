from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Invoice
from ..normalization import normalize_invoice_number, parse_decimal


def detect_duplicates(db: Session, invoice: Invoice) -> tuple[bool, int | None, str | None, list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    duplicate_of: int | None = None

    same_hash = db.scalars(
        select(Invoice).where(Invoice.sha256 == invoice.sha256, Invoice.id != invoice.id)
    ).first()
    if same_hash:
        reasons.append(
            {
                "type": "empreinte",
                "message": f"Le même fichier a déjà été importé (facture interne n° {same_hash.id}).",
                "invoice_id": same_hash.id,
            }
        )
        duplicate_of = duplicate_of or same_hash.id

    number = normalize_invoice_number(invoice.invoice_number)
    if number and invoice.supplier_id is not None:
        candidates = db.scalars(
            select(Invoice).where(
                Invoice.id != invoice.id,
                Invoice.supplier_id == invoice.supplier_id,
                Invoice.invoice_number.is_not(None),
            )
        ).all()
        for candidate in candidates:
            if normalize_invoice_number(candidate.invoice_number) != number:
                continue
            total_match = False
            if invoice.invoice_date and candidate.invoice_date == invoice.invoice_date:
                total_match = True
            extracted = (invoice.totals_extracted or {}).get("total_ttc")
            candidate_total = (candidate.totals_extracted or {}).get("total_ttc")
            value = parse_decimal(extracted) if extracted is not None else None
            other = parse_decimal(candidate_total) if candidate_total is not None else None
            if value is not None and other is not None and abs(value - other) <= Decimal("0.05"):
                total_match = True
            reasons.append(
                {
                    "type": "numero",
                    "message": (
                        f"Numéro de facture identique pour le même fournisseur "
                        f"(facture interne n° {candidate.id})."
                    ),
                    "invoice_id": candidate.id,
                    "same_date": candidate.invoice_date == invoice.invoice_date,
                    "same_total": total_match,
                }
            )
            duplicate_of = duplicate_of or candidate.id
            break

    is_duplicate = bool(reasons)
    if is_duplicate:
        invoice.is_duplicate = True
        invoice.duplicate_of_id = duplicate_of
        invoice.duplicate_reason = reasons[0]["message"]
    else:
        invoice.is_duplicate = False
        invoice.duplicate_of_id = None
        invoice.duplicate_reason = None
    return is_duplicate, duplicate_of, invoice.duplicate_reason, reasons


def duplicate_warning(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": "DOUBLON_POSSIBLE",
            "severity": "error",
            "message": reason["message"],
            "field": "document",
            "related_invoice_id": reason.get("invoice_id"),
        }
        for reason in reasons
    ]
