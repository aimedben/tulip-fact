from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ExportRecord, Invoice
from .serializers import export_payload, invoice_summary

router = APIRouter(tags=["tableau de bord"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    status_counts = dict(
        db.execute(select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)).all()
    )
    total = sum(status_counts.values())
    recent = db.scalars(select(Invoice).order_by(Invoice.imported_at.desc()).limit(8)).all()
    pending = sum(status_counts.get(status, 0) for status in ("A_VERIFIER", "PRETE_A_VALIDER"))
    exports = db.scalars(select(ExportRecord).order_by(ExportRecord.created_at.desc()).limit(5)).all()

    return {
        "counts": {
            "importees": total,
            "en_attente_verification": pending,
            "a_verifier": status_counts.get("A_VERIFIER", 0),
            "pretes_a_valider": status_counts.get("PRETE_A_VALIDER", 0),
            "validees": status_counts.get("VALIDEE", 0),
            "exportees": status_counts.get("EXPORTEE", 0),
            "en_echec": status_counts.get("ECHEC", 0),
            "en_cours": status_counts.get("IMPORTEE", 0) + status_counts.get("EXTRACTION", 0),
            "doublons": db.scalar(select(func.count(Invoice.id)).where(Invoice.is_duplicate.is_(True))) or 0,
        },
        "by_status": status_counts,
        "recent_invoices": [invoice_summary(invoice) for invoice in recent],
        "recent_exports": [
            {
                **export_payload(record),
                "invoice_number": record.invoice.invoice_number,
                "supplier_name": record.invoice.supplier.name if record.invoice.supplier else record.invoice.supplier_name_raw,
            }
            for record in exports
        ],
    }
