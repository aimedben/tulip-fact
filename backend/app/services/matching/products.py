from __future__ import annotations

from difflib import SequenceMatcher
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import Invoice, InvoiceLine, Product, ProductAlias
from ...normalization import name_key, normalize_reference


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
        ratio = max(ratio, jaccard * 0.95, containment * 0.9)
    return round(ratio, 4)


def _product_payload(product: Product, score: float, method: str) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "tulip_code": product.tulip_code,
        "designation": product.designation,
        "supplier_ref": product.supplier_ref,
        "barcode": product.barcode,
        "packaging": product.packaging,
        "stock_unit": product.stock_unit,
        "default_vat_rate": str(product.default_vat_rate) if product.default_vat_rate is not None else None,
        "score": round(score, 4),
        "method": method,
    }


def suggest_products(
    db: Session,
    raw_reference: str | None,
    raw_designation: str | None,
    supplier_id: int | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    reference = normalize_reference(raw_reference)
    designation = name_key(raw_designation or "")
    results: dict[int, dict[str, Any]] = {}

    def register(product: Product, score: float, method: str) -> None:
        existing = results.get(product.id)
        payload = _product_payload(product, score, method)
        if existing is None or payload["score"] > existing["score"]:
            results[product.id] = payload

    products = db.scalars(select(Product).where(Product.active.is_(True))).all()

    if reference:
        for product in products:
            if product.tulip_code == reference:
                register(product, 1.0, "code Tulip exact")
            if product.barcode and product.barcode == reference:
                register(product, 0.99, "code-barres exact")
            if product.supplier_ref and normalize_reference(product.supplier_ref) == reference:
                register(product, 0.97, "référence fournisseur exacte")

    if designation:
        alias_query = select(ProductAlias).where(ProductAlias.normalized_designation == designation)
        if supplier_id is not None:
            alias_query = alias_query.where(
                or_(ProductAlias.supplier_id == supplier_id, ProductAlias.supplier_id.is_(None))
            )
        aliases = db.scalars(alias_query).all()
        product_map = {product.id: product for product in products}
        for alias in aliases:
            product = product_map.get(alias.product_id)
            if product:
                register(product, 0.96, "correspondance confirmée")

        for product in products:
            keys = [product.normalized_designation, name_key(product.designation)]
            for key in keys:
                if not key:
                    continue
                if key == designation:
                    register(product, 0.95, "désignation exacte")
                else:
                    score = _similarity(designation, key)
                    if score >= 0.55:
                        register(product, score * 0.9, "similarité désignation")

    return sorted(results.values(), key=lambda item: item["score"], reverse=True)[:limit]


def match_lines(db: Session, invoice: Invoice) -> None:
    for line in invoice.lines:
        candidates = suggest_products(
            db,
            raw_reference=line.raw_reference,
            raw_designation=line.raw_designation,
            supplier_id=invoice.supplier_id,
        )
        line.match_candidates = candidates
        if not candidates:
            line.tulip_product_id = None
            line.catalog_designation = None
            line.match_status = "NON_RAPPROCHE"
            line.match_score = None
            continue

        best = candidates[0]
        if best["method"] in {"code Tulip exact", "code-barres exact", "référence fournisseur exacte", "correspondance confirmée", "désignation exacte"}:
            line.tulip_product_id = best["product_id"]
            line.catalog_designation = best["designation"]
            line.match_score = Decimal(str(best["score"]))
            line.match_status = "RAPPROCHE"
        elif best["score"] >= 0.55:
            line.tulip_product_id = None
            line.catalog_designation = None
            line.match_score = Decimal(str(best["score"]))
            line.match_status = "SUGGERE"
        else:
            line.tulip_product_id = None
            line.catalog_designation = None
            line.match_score = Decimal(str(best["score"]))
            line.match_status = "NON_RAPPROCHE"


def confirm_product(db: Session, invoice: Invoice, line: InvoiceLine, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Article Tulip introuvable.")
    line.tulip_product_id = product.id
    line.catalog_designation = product.designation
    line.match_status = "CONFIRME"
    line.match_score = Decimal("1.0")
    line.user_modified = True

    alias_key = name_key(line.raw_designation)
    if alias_key:
        alias = db.scalar(
            select(ProductAlias).where(
                ProductAlias.product_id == product.id,
                ProductAlias.normalized_designation == alias_key,
                ProductAlias.supplier_id == invoice.supplier_id,
            )
        ) if invoice.supplier_id is not None else db.scalar(
            select(ProductAlias).where(
                ProductAlias.product_id == product.id,
                ProductAlias.normalized_designation == alias_key,
                ProductAlias.supplier_id.is_(None),
            )
        )
        if alias is None:
            db.add(
                ProductAlias(
                    product_id=product.id,
                    supplier_id=invoice.supplier_id,
                    raw_designation=line.raw_designation[:255],
                    normalized_designation=alias_key[:255],
                    source="confirmation",
                )
            )
    db.flush()
    return product
