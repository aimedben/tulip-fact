from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, Supplier

PRODUCT_CODE_SENTINEL = 2147483647


def tulip_write_available(writer) -> bool:
    """Vrai si la base Tulip est activée et configurée sur ce poste.

    Quand Tulip n'est pas configuré (mode démonstration, test, poste sans
    Tulip), les fiches sont créées localement et l'interface l'indique
    explicitement : aucun faux succès Tulip n'est affiché.
    """
    config = getattr(writer, "client", None)
    config = getattr(config, "config", None)
    return bool(getattr(config, "enabled", False) and getattr(config, "configured", False))


def next_local_supplier_code(db: Session) -> str:
    """Prochain PRINCIPAL local (6 chiffres) quand Tulip n'est pas joignable."""
    codes = db.scalars(select(Supplier.code)).all()
    numbers = [int(code) for code in codes if code and str(code).isdigit()]
    return f"{(max(numbers) if numbers else 0) + 1:06d}"


def next_local_product_code(db: Session) -> str:
    """Prochain code article local quand Tulip n'est pas joignable."""
    codes = db.scalars(select(Product.tulip_code)).all()
    numbers = [
        int(code)
        for code in codes
        if code and str(code).isdigit() and int(code) != PRODUCT_CODE_SENTINEL
    ]
    return str((max(numbers) if numbers else 1000) + 1)
