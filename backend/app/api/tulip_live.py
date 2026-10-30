from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.tulip.catalog import TulipCatalog
from ..services.tulip.firebird import FirebirdError
from ..services.tulip.sync import sync_products, sync_suppliers
from ..services.tulip.writer import BeHeader, BeWriter, LineItem

router = APIRouter(prefix="/tulip/live", tags=["Tulip lecture seule"])


def _catalog() -> TulipCatalog:
    return TulipCatalog()


class BeLinePayload(BaseModel):
    product_code: int
    quantity: Decimal = Field(gt=0)
    unit_price_ht: Decimal = Field(ge=0)
    lot_code: int | None = None
    remise: Decimal | None = Field(default=None, ge=0)
    remise_type: int | None = Field(default=None)
    mqx: Decimal | None = None
    mprix: Decimal | None = None
    tva: Decimal | None = None
    tic: Decimal | None = None
    utic: Decimal | None = None
    autres: Decimal | None = None
    tvatic: int | None = None


class BeHeaderPayload(BaseModel):
    fournisseur: int
    opdate: date
    nbc: str | None = Field(default=None, max_length=32)
    datebc: date | None = None
    livfact: str | None = Field(default=None, max_length=32)
    datefact: date | None = None
    notva: bool = False
    mp: int = 1


class BeCreatePayload(BaseModel):
    header: BeHeaderPayload
    lines: list[BeLinePayload] = Field(min_length=1)


@router.post("/be", tags=["Tulip écriture"])
def live_create_be(payload: BeCreatePayload, dry_run: bool = Query(default=True)) -> dict[str, Any]:
    lines = [
        LineItem(
            product_code=item.product_code,
            quantity=item.quantity,
            unit_price_ht=item.unit_price_ht,
            lot_code=item.lot_code,
            remise=item.remise,
            remise_type=item.remise_type,
            mqx=item.mqx,
            mprix=item.mprix,
            tva=item.tva,
            tic=item.tic,
            utic=item.utic,
            autres=item.autres,
            tvatic=item.tvatic,
        )
        for item in payload.lines
    ]
    header = BeHeader(
        fournisseur=payload.header.fournisseur,
        opdate=payload.header.opdate,
        nbc=payload.header.nbc,
        datebc=payload.header.datebc,
        livfact=payload.header.livfact,
        datefact=payload.header.datefact,
        notva=payload.header.notva,
        mp=payload.header.mp,
    )
    try:
        return BeWriter().create_be(header, lines, dry_run=dry_run)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc



@router.get("/status")
def live_status() -> dict[str, Any]:
    return _catalog().status()


@router.get("/suppliers")
def live_suppliers(
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _catalog().suppliers(q=q, page=page, page_size=page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/products")
def live_products(
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _catalog().products(q=q, page=page, page_size=page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/products/{code}")
def live_product(code: str) -> dict[str, Any]:
    try:
        product = _catalog().product_by_code(code)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if product is None:
        raise HTTPException(status_code=404, detail="Article Tulip introuvable.")
    return product


@router.get("/summary")
def live_summary() -> dict[str, Any]:
    return _catalog().summary()


@router.get("/be")
def live_be_documents(
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _catalog().be_documents(q=q, page=page, page_size=page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/be/{code}")
def live_be_document(code: str) -> dict[str, Any]:
    try:
        document = _catalog().be_document(code)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="Bon d'achat Tulip introuvable.")
    return document


@router.post("/suppliers/sync")
def live_sync_suppliers(db: Session = Depends(get_db), page_size: int = Query(default=500, ge=50, le=500)) -> dict[str, Any]:
    try:
        return sync_suppliers(db, None, page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/suppliers/{supplier_id}/push")
def live_push_supplier(
    supplier_id: int,
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crée le fournisseur local dans la base Tulip (table CLIENTS, FRCLT=-1)."""
    from ..models import Supplier
    from ..normalization import to_jsonable
    from ..services.tulip.supplier_writer import SupplierWriter

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Fournisseur local introuvable.")
    try:
        result = SupplierWriter().create_supplier(
            name=supplier.name,
            principal=supplier.code,
            address=supplier.address,
            tel=supplier.phone,
            email=supplier.email,
            nrc=supplier.tax_id,
            dry_run=dry_run,
        )
    except FirebirdError as exc:
        raise HTTPException(status_code=503 if not dry_run else 409, detail=str(exc)) from exc
    return to_jsonable(result)


@router.post("/products/sync")
def live_sync_products(db: Session = Depends(get_db), page_size: int = Query(default=500, ge=50, le=500)) -> dict[str, Any]:
    try:
        return sync_products(db, None, page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/tables")
def live_tables(with_rows: bool = Query(default=True)) -> dict[str, Any]:
    try:
        return {"items": _catalog().tables(with_rows=with_rows)}
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/tables/{name}")
def live_table_rows(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    try:
        return _catalog().table_rows(name, page=page, page_size=page_size)
    except FirebirdError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


