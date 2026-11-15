from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ImportBatch, Product, Supplier
from ..normalization import name_key, normalize_reference
from ..schemas import ProductCreate, ProductUpdate, SupplierCreate, SupplierUpdate
from ..services.catalog_import import ImportFormatError, import_products, import_suppliers
from ..services.catalog_codes import (
    next_local_product_code,
    next_local_supplier_code,
    tulip_write_available,
)
from ..services.matching.products import invalidate_catalog_cache
from ..services.matching.suppliers import find_supplier_candidates
from ..services.storage import sanitize_filename
from .serializers import product_payload, supplier_payload

router = APIRouter(tags=["catalogues"])


def _batch_payload(batch: ImportBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "kind": batch.kind,
        "filename": batch.filename,
        "total_rows": batch.total_rows,
        "imported_rows": batch.imported_rows,
        "skipped_rows": batch.skipped_rows,
        "errors": batch.errors or [],
        "created_at": batch.created_at.isoformat(),
    }


@router.get("/suppliers")
def list_suppliers(
    db: Session = Depends(get_db),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(Supplier)
    count_stmt = select(func.count(Supplier.id))
    if q:
        needle = f"%{q.strip()}%"
        condition = or_(Supplier.code.ilike(needle), Supplier.name.ilike(needle))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    suppliers = db.scalars(
        stmt.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [supplier_payload(supplier) for supplier in suppliers], "total": total, "page": page, "page_size": page_size}


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crée d'abord le fournisseur dans Tulip (CLIENTS), puis localement.

    Si l'écriture Tulip échoue, rien n'est créé : le commerçant ne peut jamais
    croire qu'un fournisseur existe alors qu'il est absent de son logiciel.
    """
    from ..services.tulip.firebird import FirebirdError
    from ..services.tulip.supplier_writer import SupplierWriter

    writer = SupplierWriter()
    tulip_available = tulip_write_available(writer)
    code = (payload.code or "").strip()
    if not code:
        if tulip_available:
            try:
                code = writer.next_principal()
            except FirebirdError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Impossible de préparer le code Tulip : {exc}",
                ) from exc
        else:
            code = next_local_supplier_code(db)
    if db.scalar(select(Supplier).where(Supplier.code == code)):
        raise HTTPException(status_code=409, detail="Un fournisseur avec ce code existe déjà.")

    if tulip_available:
        try:
            tulip = writer.create_supplier(
                name=payload.name,
                principal=code,
                address=payload.address,
                city=payload.city,
                tel=payload.phone,
                email=payload.email,
                nrc=payload.tax_id,
                mf=payload.mf,
                nis=payload.nis,
                dry_run=False,
            )
        except FirebirdError as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Rien n'a été créé : l'enregistrement dans Tulip a échoué. "
                    f"Détail : {exc}"
                ),
            ) from exc
        tulip_push: dict[str, Any] = {
            "pushed": True,
            "table": "CLIENTS",
            "code": tulip.get("code"),
            "principal": tulip.get("principal"),
        }
    else:
        tulip_push = {
            "pushed": False,
            "skipped": True,
            "reason": "Tulip n'est pas activé sur ce poste : fiche enregistrée uniquement dans l'application.",
        }

    supplier = Supplier(
        code=code,
        name=payload.name,
        normalized_name=name_key(payload.name),
        name_variants=payload.name_variants,
        tax_id=payload.tax_id,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        city=payload.city,
        mf=payload.mf,
        nis=payload.nis,
        notes=payload.notes,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return {**supplier_payload(supplier), "tulip_push": tulip_push}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Fournisseur introuvable.")
    for field_name in payload.model_fields_set:
        setattr(supplier, field_name, getattr(payload, field_name))
    if payload.name is not None:
        supplier.normalized_name = name_key(payload.name)
    db.commit()
    db.refresh(supplier)
    return supplier_payload(supplier)


@router.get("/suppliers/lookup")
def lookup_supplier(
    name: str = Query(min_length=1, max_length=255),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": find_supplier_candidates(db, name)}


@router.post("/suppliers/import")
async def upload_suppliers(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    batch = await _import_catalog(file, db, "suppliers")
    return _batch_payload(batch)


@router.get("/products")
def list_products(
    db: Session = Depends(get_db),
    q: str | None = None,
    supplier_ref: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(Product)
    count_stmt = select(func.count(Product.id))
    if q:
        needle = f"%{q.strip()}%"
        condition = or_(
            Product.tulip_code.ilike(needle),
            Product.reference.ilike(needle),
            Product.designation.ilike(needle),
            Product.barcode.ilike(needle),
            Product.supplier_ref.ilike(needle),
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if supplier_ref:
        stmt = stmt.where(Product.supplier_ref == supplier_ref)
        count_stmt = count_stmt.where(Product.supplier_ref == supplier_ref)
    total = db.scalar(count_stmt) or 0
    products = db.scalars(
        stmt.order_by(Product.designation).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [product_payload(product) for product in products], "total": total, "page": page, "page_size": page_size}


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crée d'abord l'article dans Tulip (PRODUITS), puis localement.

    Si l'écriture Tulip échoue, rien n'est créé dans l'application.
    """
    from ..services.tulip.firebird import FirebirdError
    from ..services.tulip.product_writer import ProductWriter

    writer = ProductWriter()
    tulip_available = tulip_write_available(writer)
    code = (payload.tulip_code or "").strip()
    if not code:
        if tulip_available:
            try:
                code = writer.next_code()
            except FirebirdError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Impossible de préparer le code Tulip : {exc}",
                ) from exc
        else:
            code = next_local_product_code(db)
    if db.scalar(select(Product).where(Product.tulip_code == code)):
        raise HTTPException(status_code=409, detail="Un article avec ce code Tulip existe déjà.")

    if tulip_available:
        try:
            tulip = writer.create_product(
                code=code,
                designation=payload.designation,
                ref=payload.reference,
                barcode=payload.barcode,
                packaging=payload.packaging,
                stock_unit=payload.stock_unit,
                default_vat_rate=payload.default_vat_rate,
                dry_run=False,
            )
        except FirebirdError as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Rien n'a été créé : l'enregistrement dans Tulip a échoué. "
                    f"Détail : {exc}"
                ),
            ) from exc
        tulip_push: dict[str, Any] = {
            "pushed": True,
            "table": "PRODUITS",
            "code": tulip.get("code"),
            "designation": tulip.get("designation"),
            "ref": tulip.get("ref"),
        }
        generated_ref = tulip.get("ref")
    else:
        tulip_push = {
            "pushed": False,
            "skipped": True,
            "reason": "Tulip n'est pas activé sur ce poste : fiche enregistrée uniquement dans l'application.",
        }
        generated_ref = None

    product = Product(
        tulip_code=code,
        reference=(payload.reference or "").strip() or generated_ref,
        supplier_ref=payload.supplier_ref,
        barcode=payload.barcode,
        designation=payload.designation,
        normalized_designation=name_key(payload.designation),
        brand=payload.brand,
        packaging=payload.packaging,
        stock_unit=payload.stock_unit,
        default_vat_rate=payload.default_vat_rate,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    invalidate_catalog_cache()
    return {**product_payload(product), "tulip_push": tulip_push}


@router.patch("/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Article introuvable.")
    for field_name in payload.model_fields_set:
        setattr(product, field_name, getattr(payload, field_name))
    if payload.designation is not None:
        product.normalized_designation = name_key(payload.designation)
    db.commit()
    db.refresh(product)
    invalidate_catalog_cache()
    return product_payload(product)


@router.get("/products/barcode/{barcode}")
def get_product_by_barcode(barcode: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Recherche un produit par scan (douchette) ou saisie : code-barres d'abord,
    puis code Tulip ou référence fournisseur, pour toujours renvoyer le produit
    s'il est présent dans le référentiel sous l'un de ses identifiants."""
    cleaned = barcode.strip()
    product = db.scalar(select(Product).where(Product.barcode == cleaned))
    if product is None:
        needle = normalize_reference(cleaned)
        if needle:
            products = db.scalars(select(Product).where(Product.barcode.is_not(None))).all()
            product = next(
                (item for item in products if normalize_reference(item.barcode) == needle),
                None,
            )
    if product is None:
        # Repli : le produit existe déjà mais sous un autre identifiant (code Tulip ou réf. fournisseur).
        product = db.scalar(select(Product).where(Product.tulip_code == cleaned))
        if product is None:
            product = db.scalar(select(Product).where(Product.reference == cleaned))
        if product is None:
            product = db.scalar(select(Product).where(Product.supplier_ref == cleaned))
        if product is None and needle:
            product = db.scalar(select(Product).where(Product.tulip_code == needle))
        if product is None and needle:
            products = db.scalars(
                select(Product).where(Product.supplier_ref.is_not(None))
            ).all()
            product = next(
                (item for item in products if normalize_reference(item.supplier_ref) == needle),
                None,
            )
        if product is not None and not (product.barcode or "").strip():
            # Le produit apprend son code-barres : les prochains scans le renverront directement.
            product.barcode = cleaned
            db.commit()
            db.refresh(product)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Aucun produit trouvé avec le code-barre {barcode}")
    return product_payload(product)


@router.post("/products/import")
async def upload_products(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    batch = await _import_catalog(file, db, "products")
    invalidate_catalog_cache()
    return _batch_payload(batch)


@router.get("/imports")
def list_imports(db: Session = Depends(get_db), limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit)).all()
    return {"items": [_batch_payload(batch) for batch in batches]}


async def _import_catalog(file: UploadFile, db: Session, kind: str) -> ImportBatch:
    filename = sanitize_filename(file.filename, fallback=f"catalogue-{kind}")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xlsm"}:
        raise HTTPException(status_code=415, detail="Format de catalogue non pris en charge. Utilisez CSV ou XLSX.")
    temp_dir = Path(db.bind.url.database or ".").parent / "tmp" if db.bind and db.bind.url.database else None
    from ..config import settings

    temp_dir = settings.data_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / f"catalog-{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    await file.close()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Le catalogue dépasse 10 Mo.")
    target.write_bytes(content)
    try:
        if kind == "suppliers":
            return import_suppliers(db, target, filename)
        return import_products(db, target, filename)
    except ImportFormatError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing_columns": exc.missing},
        ) from exc
    finally:
        target.unlink(missing_ok=True)
