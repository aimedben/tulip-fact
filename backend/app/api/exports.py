from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ExportRecord, Invoice
from ..schemas import ExportRequest
from ..services.exports import ExportError, export_invoice
from ..services.storage import StorageError, resolve_relative
from .serializers import export_payload

router = APIRouter(tags=["exports"])

MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
    "rapport": "text/plain; charset=utf-8",
}


@router.post("/invoices/{invoice_id}/export")
def export(invoice_id: int, payload: ExportRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable.")
    try:
        records = export_invoice(db, invoice, payload.formats, actor=payload.actor)
    except ExportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "message": "Export généré. Vérifiez le format avant tout import dans Tulip.",
        "records": [export_payload(record) for record in records],
        "invoice_status": invoice.status,
    }


@router.get("/exports")
def list_exports(
    db: Session = Depends(get_db),
    invoice_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(ExportRecord).order_by(ExportRecord.created_at.desc()).limit(limit)
    if invoice_id is not None:
        stmt = stmt.where(ExportRecord.invoice_id == invoice_id)
    records = db.scalars(stmt).all()
    return {
        "items": [
            {
                **export_payload(record),
                "invoice_number": record.invoice.invoice_number,
                "supplier_name": record.invoice.supplier.name
                if record.invoice.supplier
                else record.invoice.supplier_name_raw,
            }
            for record in records
        ]
    }


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, db: Session = Depends(get_db)):
    record = db.get(ExportRecord, export_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Export introuvable.")
    try:
        path = resolve_relative(record.file_path)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier d'export introuvable sur le disque.")
    filename = path.name
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(record.format, "application/octet-stream"),
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )
