from __future__ import annotations

from typing import Any

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Product, Supplier
from ...normalization import name_key
from ..matching.products import invalidate_catalog_cache
from .catalog import TulipCatalog


def sync_suppliers(db: Session, catalog: TulipCatalog | None = None, page_size: int = 500) -> dict[str, Any]:
    catalog = catalog or TulipCatalog()
    created = 0
    updated = 0
    page = 1
    total_seen = 0
    while True:
        result = catalog.suppliers(page=page, page_size=page_size)
        if not result["items"]:
            break
        for item in result["items"]:
            code = item["tulip_code"]
            if not code:
                continue
            supplier = db.scalar(select(Supplier).where(Supplier.code == code))
            if supplier is None:
                supplier = Supplier(code=code, name=item["name"], normalized_name=name_key(item["name"]))
                db.add(supplier)
                created += 1
            else:
                if item["name"] and supplier.name != item["name"]:
                    supplier.name = item["name"]
                    supplier.normalized_name = name_key(item["name"])
                updated += 1
            supplier.tax_id = item.get("tax_id") or supplier.tax_id
            supplier.phone = item.get("phone") or supplier.phone
            supplier.email = item.get("email") or supplier.email
            supplier.address = item.get("address") or supplier.address
            supplier.city = item.get("city") or supplier.city
            tax_ids = item.get("tax_ids") or {}
            supplier.mf = tax_ids.get("mf") or supplier.mf
            supplier.nis = tax_ids.get("nis") or supplier.nis
            marker = item.get("code")
            notes = "Code principal Tulip: " + marker if marker and marker != code else None
            if notes and not supplier.notes:
                supplier.notes = notes
            total_seen += 1
        db.commit()
        if page * page_size >= result["total"]:
            break
        page += 1
    return {"created": created, "updated": updated, "total": total_seen, "local_total": _local_total(db)}


def _local_total(db: Session) -> int:
    from sqlalchemy import func

    return int(db.scalar(select(func.count(Supplier.id))) or 0)


def _local_product_total(db: Session) -> int:
    from sqlalchemy import func

    return int(db.scalar(select(func.count(Product.id))) or 0)


def sync_products(db: Session, catalog: TulipCatalog | None = None, page_size: int = 500) -> dict[str, Any]:
    """Importe le référentiel articles Tulip (référence, désignation, code-barres,
    conditionnement, unité, TVA par défaut) dans le catalogue local.
    """
    catalog = catalog or TulipCatalog()
    created = 0
    updated = 0
    total_seen = 0
    page = 1
    while True:
        result = catalog.products(page=page, page_size=page_size)
        if not result["items"]:
            break
        for item in result["items"]:
            code = item["tulip_code"]
            if not code:
                continue
            designation = item["designation"] or code
            internal = item.get("tulip_id") or item.get("id")
            ref = item.get("ref") or ""
            product = None
            if internal is not None and str(internal) != str(code):
                # Un article créé ici porte son code numérique Tulip (« 12445 »),
                # pas le REF du listing Tulip (« ART12445 ») : le code interne
                # est donc l'identité la plus fiable, cherchée en premier.
                product = db.scalar(
                    select(Product).where(Product.tulip_code == str(internal))
                )
            if product is None:
                product = db.scalar(select(Product).where(Product.tulip_code == code))
            if product is None and ref and ref != code:
                product = db.scalar(select(Product).where(Product.reference == ref))
            if product is None:
                product = Product(
                    tulip_code=code,
                    designation=designation[:255],
                    normalized_designation=name_key(designation),
                    active=True,
                )
                db.add(product)
                created += 1
            else:
                if product.designation != designation:
                    product.designation = designation[:255]
                    product.normalized_designation = name_key(designation)
                updated += 1
            product.reference = item.get("reference") or item.get("ref") or product.reference
            product.supplier_ref = item.get("supplier_ref") or product.supplier_ref
            product.barcode = item.get("barcode") or product.barcode
            product.stock_unit = item.get("stock_unit") or product.stock_unit
            product.packaging = item.get("packaging") or product.packaging
            vat = item.get("default_vat_rate")
            if vat is not None and vat != "":
                product.default_vat_rate = Decimal(str(vat))
            total_seen += 1
        db.commit()
        invalidate_catalog_cache()
        if page * page_size >= result["total"]:
            break
        page += 1
    return {
        "created": created,
        "updated": updated,
        "total": total_seen,
        "local_total": _local_product_total(db),
    }


def sync_suppliers_session(catalog: TulipCatalog | None = None) -> dict[str, Any]:
    session = next(get_db())
    try:
        return sync_suppliers(session, catalog)
    finally:
        session.close()
