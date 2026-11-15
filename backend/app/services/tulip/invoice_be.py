from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ...models import Invoice
from .catalog import TulipCatalog
from .writer import BeHeader, LineItem


def _is_tulip_code(value: str | None) -> bool:
    if not value:
        return False
    stripped = value.strip()
    return stripped.lstrip("-").replace(".", "", 1).isdigit()


def build_be_from_invoice(
    db: Session,
    invoice: Invoice,
    catalog: TulipCatalog,
) -> dict[str, Any]:
    """Construit (sans écrire) un BE Tulip à partir d'une facture importée/scannée.

    Reproduit la saisie manuelle Tulip d'un bon d'entrée :
    - BE (SFX=-32765, CMP=0) : FOURNISSEUR = code client fournisseur négatif,
      NBC = n° bon de commande (sinon n° facture), LIVFACT = n° BL (sinon n° facture),
      DATEFACT = date facture, DETTE est déclenché par le writer à l'écriture.
    - DETAILSBR : PRODUIT = code produit Tulip négatif, QTE/PUHT/TVA/REMISE
      depuis les lignes rapprochées ; MPRIX = prix de vente saisi sur la ligne
      (ou prix producteur par défaut non forcé). MQX/TVA/defaults non renseignés
      sont repris de PRODUITS par DETAILS_BR_BI (comportement Tulip).
    """
    issues: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    supplier = invoice.supplier
    fournisseur: int | None = None
    if supplier is not None and _is_tulip_code(supplier.code):
        fournisseur = int(supplier.code.strip())
    else:
        issues.append(
            {
                "code": "FOURNISSEUR_MANQUANT",
                "message": "Le fournisseur local n'est pas relié à un code Tulip (sync Tulip ou édition de la fiche).",
            }
        )

    invoice_date = invoice.invoice_date or date.today()
    header = BeHeader(
        fournisseur=fournisseur or 0,
        opdate=invoice_date,
        nbc=(invoice.bc_number or invoice.invoice_number),
        datebc=(invoice.bc_date or invoice.invoice_date or invoice_date),
        livfact=(invoice.bl_number or invoice.invoice_number),
        datefact=invoice.invoice_date,
        notva=False,
        mp=1,
    )

    lines: list[LineItem] = []
    product_cache: dict[str, int | None] = {}
    for line in invoice.lines:
        product = line.product
        raw = line.catalog_designation or line.raw_designation
        if product is None or not (product.tulip_code or "").strip():
            skipped.append(
                {
                    "position": line.position,
                    "designation": raw,
                    "reason": "PRODUIT_NON_RAPPROCHE",
                }
            )
            continue

        tulip_code = (product.tulip_code or "").strip()
        if tulip_code not in product_cache:
            tulip_product = catalog.product_by_code(tulip_code)
            tulip_id = tulip_product.get("tulip_id") if tulip_product else None
            if tulip_id is None and tulip_code.lstrip("-").isdigit():
                tulip_id = int(tulip_code)
            product_cache[tulip_code] = tulip_id
        product_code = product_cache[tulip_code]
        if product_code is None:
            skipped.append(
                {
                    "position": line.position,
                    "designation": raw,
                    "reason": "PRODUIT_ABSENT_TULIP",
                    "tulip_code": tulip_code,
                }
            )
            continue

        if fournisseur is None:
            continue

        discount = line.discount_value
        remise_type: int | None = None
        if discount is not None and discount != Decimal("0"):
            remise_type = 0 if (line.discount_type or "percent") == "percent" else 1

        lines.append(
            LineItem(
                product_code=product_code,
                quantity=line.quantity if line.quantity is not None else Decimal("0"),
                unit_price_ht=line.unit_price_ht if line.unit_price_ht is not None else Decimal("0"),
                remise=discount,
                remise_type=remise_type,
                # Prix de vente saisi sur la ligne (saisie manuelle prioritaire) :
                # écrit dans DETAILSBR.MPRIX du BE Tulip.
                mprix=line.prix_vente,
                tva=line.vat_rate,
            )
        )

    ready = fournisseur is not None and len(lines) > 0
    return {
        "ok": ready,
        "ready": ready,
        "header": header,
        "lines": lines,
        "issues": issues,
        "skipped_lines": skipped,
        "count_lines": len(lines),
        "count_skipped": len(skipped),
    }


def be_preview_payload(result: dict[str, Any], writer_preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "dry_run": True,
        "ready": result["ready"],
        "issues": result["issues"],
        "skipped_lines": result["skipped_lines"],
        "preview": writer_preview,
    }
