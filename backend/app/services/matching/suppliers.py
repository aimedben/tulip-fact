from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Invoice, Supplier, SupplierAlias
from ...normalization import name_key, normalize_key


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
        ratio = max(ratio, jaccard * 0.9, containment * 0.85)
    return round(ratio, 4)


def find_supplier_candidates(
    db: Session,
    raw_name: str | None,
    candidates: list[str] | None = None,
    supplier_code: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if supplier_code:
        supplier = db.scalar(select(Supplier).where(Supplier.code == supplier_code))
        if supplier:
            return [
                {
                    "supplier_id": supplier.id,
                    "code": supplier.code,
                    "name": supplier.name,
                    "score": 1.0,
                    "method": "code",
                    "auto": True,
                }
            ]

    queries = [value for value in ([raw_name] + list(candidates or [])) if value]
    normalized_queries = []
    seen = set()
    for value in queries:
        key = name_key(value)
        if key and key not in seen:
            seen.add(key)
            normalized_queries.append((value, key))

    aliases = db.scalars(select(SupplierAlias)).all()
    alias_map = {alias.normalized_name: alias.supplier_id for alias in aliases}
    suppliers = db.scalars(select(Supplier).where(Supplier.active.is_(True))).all()

    results: dict[int, dict[str, Any]] = {}

    def register(supplier: Supplier, score: float, method: str, auto: bool, matched: str | None = None) -> None:
        existing = results.get(supplier.id)
        payload = {
            "supplier_id": supplier.id,
            "code": supplier.code,
            "name": supplier.name,
            "score": round(score, 4),
            "method": method,
            "auto": auto,
            "matched_text": matched,
        }
        if existing is None or payload["score"] > existing["score"]:
            results[supplier.id] = payload

    for raw, key in normalized_queries:
        alias_supplier_id = alias_map.get(key)
        if alias_supplier_id:
            supplier = next((item for item in suppliers if item.id == alias_supplier_id), None)
            if supplier:
                register(supplier, 1.0, "alias", True, raw)
        for supplier in suppliers:
            supplier_keys = [supplier.normalized_name, name_key(supplier.name)]
            supplier_keys.extend(name_key(variant) for variant in (supplier.name_variants or []))
            for supplier_key in supplier_keys:
                if not supplier_key:
                    continue
                if supplier_key == key:
                    register(supplier, 0.98, "nom exact", True, raw)
                else:
                    score = _similarity(key, supplier_key)
                    if score >= 0.55:
                        register(supplier, score, "similarité", False, raw)

    ranked = sorted(results.values(), key=lambda item: item["score"], reverse=True)[:limit]
    return ranked


def confirm_supplier(db: Session, invoice: Invoice, supplier_id: int, raw_name: str | None = None) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError("Fournisseur introuvable.")
    invoice.supplier_id = supplier.id
    invoice.supplier_code_snapshot = supplier.code
    invoice.supplier_name_raw = raw_name or invoice.supplier_name_raw or supplier.name
    invoice.supplier_match = {
        "supplier_id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "score": 1.0,
        "method": "confirmation utilisateur",
        "confirmed": True,
    }

    alias_source = invoice.supplier_name_raw or supplier.name
    alias_key = normalize_key(alias_source)
    if alias_key:
        existing = db.scalar(select(SupplierAlias).where(SupplierAlias.normalized_name == alias_key))
        if existing is None:
            db.add(
                SupplierAlias(
                    supplier_id=supplier.id,
                    raw_name=alias_source[:255],
                    normalized_name=alias_key[:255],
                    source="confirmation",
                )
            )
    db.flush()
    return supplier
