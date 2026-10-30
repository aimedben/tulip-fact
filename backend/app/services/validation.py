from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Invoice
from ..normalization import to_jsonable
from .accounting import compute_line, verify_invoice
from .audit import record_audit


class ValidationError(ValueError):
    def __init__(self, message: str, issues: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.issues = issues or []


def recompute_invoice(invoice: Invoice, tolerance: Decimal | None = None) -> None:
    tolerance = tolerance if tolerance is not None else settings.amount_tolerance
    totals, checks = verify_invoice(invoice, tolerance=tolerance)
    invoice.totals_calculated = to_jsonable(totals)
    invoice.checks = to_jsonable(checks)
    for index, line in enumerate(invoice.lines, start=1):
        result = compute_line(line)
        line.line_total_ht_calculated = result["net"]
        line.position = line.position or index
    if invoice.supplier_id is None:
        invoice.supplier_match = invoice.supplier_match or {}


def _hard_issues(invoice: Invoice) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if invoice.supplier_id is None:
        issues.append(
            {
                "code": "FOURNISSEUR_REQUIS",
                "severity": "error",
                "message": "Sélectionnez et confirmez un fournisseur du référentiel.",
                "field": "supplier_id",
            }
        )
    if not invoice.invoice_number:
        issues.append(
            {
                "code": "NUMERO_FACTURE_REQUIS",
                "severity": "error",
                "message": "Le numéro de facture est obligatoire.",
                "field": "invoice_number",
            }
        )
    if invoice.invoice_date is None:
        issues.append(
            {
                "code": "DATE_FACTURE_REQUISE",
                "severity": "error",
                "message": "La date de facture est obligatoire.",
                "field": "invoice_date",
            }
        )
    if not invoice.lines:
        issues.append(
            {
                "code": "LIGNES_REQUISES",
                "severity": "error",
                "message": "La facture doit contenir au moins une ligne.",
                "field": "lines",
            }
        )
    for line in invoice.lines:
        position = line.position
        if not line.raw_designation or not line.raw_designation.strip():
            issues.append(
                {
                    "code": "DESIGNATION_REQUISE",
                    "severity": "error",
                    "message": f"Ligne {position} : la désignation est obligatoire.",
                    "field": "raw_designation",
                    "line_position": position,
                }
            )
        if line.tulip_product_id is None:
            issues.append(
                {
                    "code": "ARTICLE_NON_RAPPROCHE",
                    "severity": "error",
                    "message": f"Ligne {position} : aucun article Tulip n'est associé.",
                    "field": "tulip_product_id",
                    "line_position": position,
                }
            )
        if line.quantity is None or line.quantity <= 0:
            issues.append(
                {
                    "code": "QUANTITE_REQUISE",
                    "severity": "error",
                    "message": f"Ligne {position} : la quantité doit être renseignée et positive.",
                    "field": "quantity",
                    "line_position": position,
                }
            )
        if line.unit_price_ht is None:
            issues.append(
                {
                    "code": "PRIX_REQUIS",
                    "severity": "error",
                    "message": f"Ligne {position} : le prix unitaire HT est obligatoire.",
                    "field": "unit_price_ht",
                    "line_position": position,
                }
            )
    return issues


def readiness(invoice: Invoice) -> dict[str, Any]:
    hard = _hard_issues(invoice)
    checks = invoice.checks or []
    accounting_errors = [check for check in checks if check.get("severity") == "error"]
    warnings = [check for check in checks if check.get("severity") == "warning"]
    warnings.extend(
        warning
        for warning in (invoice.warnings or [])
        if isinstance(warning, dict) and warning.get("severity") in {"warning", "error"}
    )
    duplicate_issue = None
    if invoice.is_duplicate:
        duplicate_issue = {
            "code": "DOUBLON_A_CONFIRMER",
            "severity": "error",
            "message": invoice.duplicate_reason or "Un doublon possible a été détecté.",
            "field": "document",
        }
    totals_ack_required = bool(accounting_errors)
    blockers = list(hard)
    if duplicate_issue:
        blockers.append(duplicate_issue)
    return {
        "ready": not hard,
        "can_validate": not hard,
        "blocking": blockers,
        "hard": hard,
        "accounting_errors": accounting_errors,
        "warnings": warnings,
        "duplicate": duplicate_issue,
        "totals_ack_required": totals_ack_required,
        "requires_acks": {
            "duplicate": invoice.is_duplicate,
            "totals": totals_ack_required,
            "warnings": bool(warnings),
        },
    }


def validate_invoice(
    db: Session,
    invoice: Invoice,
    actor: str,
    *,
    acknowledge_duplicate: bool = False,
    acknowledge_totals: bool = False,
    acknowledge_warnings: bool = False,
) -> dict[str, Any]:
    if invoice.status == "VALIDEE":
        raise ValidationError("Cette facture est déjà validée.")
    if invoice.status == "EXPORTEE":
        raise ValidationError("Cette facture est déjà exportée ; créez une correction explicite si nécessaire.")
    if invoice.status == "ECHEC":
        raise ValidationError("Une facture en échec ne peut pas être validée : relancez le traitement.")

    recompute_invoice(invoice)
    state = readiness(invoice)
    if state["hard"]:
        raise ValidationError("Des informations obligatoires sont manquantes.", state["hard"])
    if state["duplicate"] and not acknowledge_duplicate:
        raise ValidationError(
            "Un doublon possible a été détecté. Confirmez explicitement la validation.",
            [state["duplicate"]],
        )
    if state["accounting_errors"] and not acknowledge_totals:
        raise ValidationError(
            "Des écarts comptables doivent être examinés avant validation.",
            state["accounting_errors"],
        )

    invoice.status = "VALIDEE"
    invoice.validated_at = datetime.now(timezone.utc)
    invoice.validation_user = actor
    details = {
        "acknowledge_duplicate": acknowledge_duplicate,
        "acknowledge_totals": acknowledge_totals,
        "acknowledge_warnings": acknowledge_warnings,
        "warnings": state["warnings"],
        "totals_calculated": invoice.totals_calculated,
    }
    record_audit(db, invoice.id, "validation", actor=actor, details=details)
    db.flush()
    return {"invoice_id": invoice.id, "status": invoice.status, "warnings": state["warnings"]}

