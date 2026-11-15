from __future__ import annotations

from difflib import SequenceMatcher
from decimal import Decimal
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import Invoice, InvoiceLine, Product, ProductAlias
from ...normalization import name_key, normalize_reference

# Catalogue par session : l'écrasante majorité des requêtes ne modifie pas le
# catalogue (7 000 articles), et le recharger à chaque ligne de facture coûte
# des centaines de ms. L'invalidation se fait à l'écriture.
_PRODUCTS_CACHE: WeakKeyDictionary[Session, list[Product]] = WeakKeyDictionary()


def _similarity(left: str, right: str, left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    approx = 0.0
    if left_tokens and right_tokens:
        overlap = left_tokens & right_tokens
        jaccard = len(overlap) / len(left_tokens | right_tokens)
        containment = len(overlap) / min(len(left_tokens), len(right_tokens))
        approx = max(jaccard * 0.95, containment * 0.9)
    if approx >= 0.55:
        # Déjà au-dessus du seuil d'enregistrement : le ratio exact ne peut
        # que remonter le score, la candidature serait retenue de toute façon.
        return round(approx, 4)
    # Borne exacte du ratio : les correspondances ne peuvent excéder le texte
    # le plus court, donc ratio ≤ 2·min/(la+lb). Si la borne est sous le seuil,
    # construire le matcher (qui calcule b2j dès l'init) serait du gaspillage.
    if (2 * min(len(left), len(right))) / (len(left) + len(right)) < 0.55:
        return round(approx, 4)
    # On n'évalue la comparaison exacte (coût quadratique) que lorsqu'une
    # candidature est plausible (~7 000 produits × chaque ligne de facture).
    matcher = SequenceMatcher(None, left, right)
    if matcher.real_quick_ratio() < 0.55 or matcher.quick_ratio() < 0.55:
        return round(approx, 4)
    return round(max(approx, matcher.ratio()), 4)


def _product_payload(product: Product, score: float, method: str) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "tulip_code": product.tulip_code,
        "reference": product.reference,
        "designation": product.designation,
        "supplier_ref": product.supplier_ref,
        "barcode": product.barcode,
        "packaging": product.packaging,
        "stock_unit": product.stock_unit,
        "default_vat_rate": str(product.default_vat_rate) if product.default_vat_rate is not None else None,
        "score": round(score, 4),
        "method": method,
    }


def _designation_keys(product: Product) -> list[tuple[str, set[str]]]:
    """Clés de désignation d'un produit, avec leurs tokens, mémoïsées sur l'entité.

    L'identité map de la session garantit la fraîcheur : toute modification de
    produit passe par une nouvelle session, donc de nouvelles entités.
    """
    cached = getattr(product, "_designation_keys_cache", None)
    if cached is None:
        keys = {key for key in (product.normalized_designation, name_key(product.designation)) if key}
        cached = [(key, set(key.split())) for key in keys]
        product._designation_keys_cache = cached
    return cached


def suggest_products(
    db: Session,
    raw_reference: str | None,
    raw_designation: str | None,
    supplier_id: int | None = None,
    limit: int = 5,
    products: list[Product] | None = None,
) -> list[dict[str, Any]]:
    reference = normalize_reference(raw_reference)
    designation = name_key(raw_designation or "")
    results: dict[int, dict[str, Any]] = {}

    def register(product: Product, score: float, method: str) -> None:
        existing = results.get(product.id)
        payload = _product_payload(product, score, method)
        if existing is None or payload["score"] > existing["score"]:
            results[product.id] = payload

    if products is None:
        # Liste partagable entre les lignes d'une même facture : la charger
        # une fois plutôt que par ligne (≈ 7 000 articles en base).
        products = _active_products(db)

    if reference:
        for product in products:
            if product.tulip_code == reference:
                register(product, 1.0, "code Tulip exact")
            if normalize_reference(product.barcode) == reference:
                register(product, 0.99, "code-barres exact")
            if normalize_reference(product.supplier_ref) == reference:
                register(product, 0.97, "référence fournisseur exacte")
            if product.reference and normalize_reference(product.reference) == reference:
                register(product, 0.98, "référence article exacte")

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

        left_tokens = set(designation.split())
        for product in products:
            for key, key_tokens in _designation_keys(product):
                if key == designation:
                    register(product, 0.95, "désignation exacte")
                else:
                    score = _similarity(designation, key, left_tokens, key_tokens)
                    if score >= 0.55:
                        register(product, score * 0.9, "similarité désignation")

    return sorted(results.values(), key=lambda item: item["score"], reverse=True)[:limit]


def _active_products(db: Session) -> list[Product]:
    products = _PRODUCTS_CACHE.get(db)
    if products is None:
        products = db.scalars(select(Product).where(Product.active.is_(True))).all()
        _PRODUCTS_CACHE[db] = products
    return products


def invalidate_catalog_cache() -> None:
    """À appeler après toute écriture sur products / product_aliases."""
    for key in list(_PRODUCTS_CACHE.keys()):
        _PRODUCTS_CACHE.pop(key, None)


def match_lines(db: Session, invoice: Invoice) -> None:
    # Catalogue chargé une seule fois pour toutes les lignes.
    products = _active_products(db)
    for line in invoice.lines:
        candidates = suggest_products(
            db,
            raw_reference=line.raw_reference,
            raw_designation=line.raw_designation,
            supplier_id=invoice.supplier_id,
            products=products,
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
    # Chaque valeur reste dans sa colonne : la référence article vient de la
    # colonne REF, jamais du code-barres (qui reste dans product.barcode).
    reference = (product.reference or "").strip()
    supplier_reference = (product.supplier_ref or "").strip()
    if reference:
        line.raw_reference = reference
    elif supplier_reference and not (line.raw_reference or "").strip():
        line.raw_reference = supplier_reference

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
