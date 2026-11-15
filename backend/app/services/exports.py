from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ExportRecord, Invoice
from ..normalization import format_money_fr, to_jsonable
from .audit import record_audit

TULIP_WARNING = (
    "Fichier de travail généré par l'application. Le format d'import direct dans Tulip "
    "Gestion commerciale V3.33 n'a pas été confirmé par l'éditeur : vérifiez-le avant tout import."
)


class ExportError(ValueError):
    pass


def _date_fr(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _decimal_csv(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{Decimal(value):.2f}".replace(".", ",")


def _safe_stem(invoice: Invoice) -> str:
    number = invoice.invoice_number or f"facture-{invoice.id}"
    cleaned = "".join(c for c in number if c.isalnum() or c in "-_")[:40] or f"facture-{invoice.id}"
    return f"facture-{invoice.id}-{cleaned}"


def _export_directory(invoice: Invoice) -> Path:
    directory = settings.exports_dir / invoice.uuid
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _line_payload(line) -> dict[str, Any]:
    product = line.product
    return {
        "position": line.position,
        "reference_fournisseur": line.raw_reference,
        "code_article_tulip": product.tulip_code if product else None,
        "designation_facture": line.raw_designation,
        "designation_catalogue": line.catalog_designation,
        "lot": line.lot_number,
        "colis": str(line.packages) if line.packages is not None else None,
        "quantite": str(line.quantity) if line.quantity is not None else None,
        "unite": line.unit,
        "conditionnement": line.packaging,
        "prix_unitaire_ht": str(line.unit_price_ht) if line.unit_price_ht is not None else None,
        "prix_vente": str(line.prix_vente) if line.prix_vente is not None else None,
        "tva": str(line.vat_rate) if line.vat_rate is not None else None,
        "montant_ht_extrait": str(line.line_total_ht_extracted) if line.line_total_ht_extracted is not None else None,
        "montant_ht_calcule": str(line.line_total_ht_calculated) if line.line_total_ht_calculated is not None else None,
        "remise_valeur": str(line.discount_value) if line.discount_value is not None else None,
        "remise_type": line.discount_type,
        "statut_rapprochement": line.match_status,
        "score_rapprochement": str(line.match_score) if line.match_score is not None else None,
        "confiance": line.confidence,
        "valeurs_originales": line.original_values,
        "corrige_manuellement": line.user_modified,
    }


def invoice_payload(invoice: Invoice) -> dict[str, Any]:
    supplier = invoice.supplier
    return to_jsonable(
        {
            "facture": {
                "id": invoice.id,
                "uuid": invoice.uuid,
                "fichier_original": invoice.original_filename,
                "empreinte_sha256": invoice.sha256,
                "date_facture": invoice.invoice_date,
                "code_fournisseur": invoice.supplier_code_snapshot or (supplier.code if supplier else None),
                "nom_fournisseur": supplier.name if supplier else invoice.supplier_name_raw,
                "type_document": invoice.document_type,
                "bl_facture": invoice.bl_facture,
                "numero_bc": invoice.bc_number,
                "date_bc": invoice.bc_date,
                "numero_bl_facture": invoice.bl_number,
                "date_bl_facture": invoice.bl_date,
                "numero_facture": invoice.invoice_number,
                "devise": invoice.currency,
                "totaux_extraits": invoice.totals_extracted,
                "totaux_recalcules": invoice.totals_calculated,
                "controles": invoice.checks,
                "avertissements": invoice.warnings,
                "statut": invoice.status,
                "doublon": invoice.is_duplicate,
                "date_import": invoice.imported_at,
                "date_validation": invoice.validated_at,
                "utilisateur_validation": invoice.validation_user,
                "note": TULIP_WARNING,
            },
            "lignes": [_line_payload(line) for line in invoice.lines],
        }
    )


def _write_csv(invoice: Invoice, target: Path) -> None:
    headers = [
        "Date facture",
        "Code fournisseur",
        "Nom fournisseur",
        "Type document",
        "BL - Facture",
        "N° BC",
        "Date BC",
        "N° BL / Facture",
        "Date BL / Facture",
        "N° facture fournisseur",
        "Devise",
        "Réf.",
        "Désignation",
        "Code article Tulip",
        "Désignation catalogue",
        "N° de lot",
        "Colis",
        "Quantité",
        "Unité",
        "P.U HT",
        "Prix vente",
        "TVA",
        "Montant HT",
        "Remise",
        "Type remise",
        "Total HT facture",
        "TVA facture",
        "Timbre",
        "Total TTC facture",
        "Statut rapprochement",
        "Avertissement",
    ]
    supplier = invoice.supplier
    totals = invoice.totals_extracted or {}
    lines = invoice.lines or [None]
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for line in lines:
            product = line.product if line else None
            writer.writerow(
                [
                    _date_fr(invoice.invoice_date),
                    invoice.supplier_code_snapshot or (supplier.code if supplier else ""),
                    supplier.name if supplier else (invoice.supplier_name_raw or ""),
                    invoice.document_type or "",
                    "OUI" if invoice.bl_facture else ("NON" if invoice.bl_facture is False else ""),
                    invoice.bc_number or "",
                    _date_fr(invoice.bc_date),
                    invoice.bl_number or "",
                    _date_fr(invoice.bl_date),
                    invoice.invoice_number or "",
                    invoice.currency,
                    line.raw_reference if line else "",
                    line.raw_designation if line else "",
                    product.tulip_code if product else "",
                    line.catalog_designation if line and line.catalog_designation else "",
                    line.lot_number if line else "",
                    _decimal_csv(line.packages) if line else "",
                    _decimal_csv(line.quantity) if line else "",
                    line.unit if line else "",
                    _decimal_csv(line.unit_price_ht) if line else "",
                    _decimal_csv(line.prix_vente) if line else "",
                    _decimal_csv(line.vat_rate) if line else "",
                    _decimal_csv(line.line_total_ht_extracted) if line else "",
                    _decimal_csv(line.discount_value) if line else "",
                    line.discount_type if line else "",
                    _decimal_csv(_to_decimal(totals.get("total_ht"))) if totals.get("total_ht") is not None else "",
                    _decimal_csv(_to_decimal(totals.get("vat_total"))) if totals.get("vat_total") is not None else "",
                    _decimal_csv(_to_decimal(totals.get("timbre"))) if totals.get("timbre") is not None else "",
                    _decimal_csv(_to_decimal(totals.get("total_ttc"))) if totals.get("total_ttc") is not None else "",
                    line.match_status if line else "",
                    TULIP_WARNING,
                ]
            )


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _write_xlsx(invoice: Invoice, target: Path) -> None:
    workbook = Workbook()
    header_sheet = workbook.active
    header_sheet.title = "En-tête"
    supplier = invoice.supplier
    totals = invoice.totals_extracted or {}
    calculated = invoice.totals_calculated or {}

    rows = [
        ("Champ", "Valeur"),
        ("Fichier original", invoice.original_filename),
        ("Date facture", _date_fr(invoice.invoice_date)),
        ("Code fournisseur", invoice.supplier_code_snapshot or (supplier.code if supplier else "")),
        ("Nom fournisseur", supplier.name if supplier else (invoice.supplier_name_raw or "")),
        ("Type de document", invoice.document_type or ""),
        ("BL - Facture", "OUI" if invoice.bl_facture else ("NON" if invoice.bl_facture is False else "")),
        ("N° BC", invoice.bc_number or ""),
        ("Date BC", _date_fr(invoice.bc_date)),
        ("N° BL / Facture", invoice.bl_number or ""),
        ("Date BL / Facture", _date_fr(invoice.bl_date)),
        ("N° facture fournisseur", invoice.invoice_number or ""),
        ("Devise", invoice.currency),
        ("Total HT extrait", format_money_fr(_to_decimal(totals.get("total_ht")), invoice.currency)),
        ("Total TVA extrait", format_money_fr(_to_decimal(totals.get("vat_total")), invoice.currency)),
        ("Timbre", format_money_fr(_to_decimal(totals.get("timbre")), invoice.currency)),
        ("Total TTC extrait", format_money_fr(_to_decimal(totals.get("total_ttc")), invoice.currency)),
        ("Total HT recalculé", format_money_fr(_to_decimal(calculated.get("total_ht")), invoice.currency)),
        ("Total TVA recalculé", format_money_fr(_to_decimal(calculated.get("vat_total")), invoice.currency)),
        ("Total TTC recalculé", format_money_fr(_to_decimal(calculated.get("total_ttc")), invoice.currency)),
        ("Statut", invoice.status),
        ("Avertissement", TULIP_WARNING),
    ]
    for row in rows:
        header_sheet.append(row)
    header_sheet.column_dimensions["A"].width = 30
    header_sheet.column_dimensions["B"].width = 85
    header_sheet["A1"].font = Font(bold=True, color="FFFFFF")
    header_sheet["B1"].font = Font(bold=True, color="FFFFFF")
    header_sheet["A1"].fill = PatternFill("solid", fgColor="1F3A5F")
    header_sheet["B1"].fill = PatternFill("solid", fgColor="1F3A5F")

    line_sheet = workbook.create_sheet("Lignes")
    line_headers = [
        "N°",
        "Réf.",
        "Désignation facture",
        "Code article Tulip",
        "Désignation catalogue",
        "N° de lot",
        "Colis",
        "Quantité",
        "Unité",
        "P.U HT",
        "Prix vente",
        "TVA",
        "Montant HT",
        "Remise",
        "Type remise",
        "Rapprochement",
    ]
    line_sheet.append(line_headers)
    for cell in line_sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    for line in invoice.lines:
        line_sheet.append(
            [
                line.position,
                line.raw_reference or "",
                line.raw_designation,
                line.product.tulip_code if line.product else "",
                line.catalog_designation or "",
                line.lot_number or "",
                float(line.packages) if line.packages is not None else None,
                float(line.quantity) if line.quantity is not None else None,
                line.unit or "",
                float(line.unit_price_ht) if line.unit_price_ht is not None else None,
                float(line.prix_vente) if line.prix_vente is not None else None,
                float(line.vat_rate) if line.vat_rate is not None else None,
                float(line.line_total_ht_extracted) if line.line_total_ht_extracted is not None else None,
                float(line.discount_value) if line.discount_value is not None else None,
                line.discount_type or "",
                line.match_status,
            ]
        )
    widths = [6, 14, 40, 18, 40, 14, 8, 10, 10, 12, 12, 8, 14, 10, 12, 18]
    for index, width in enumerate(widths, start=1):
        line_sheet.column_dimensions[chr(64 + index)].width = width
    line_sheet.freeze_panes = "A2"

    check_sheet = workbook.create_sheet("Contrôles")
    check_sheet.append(["Code", "Gravité", "Champ", "Ligne", "Message", "Attendu", "Réel", "Écart"])
    for cell in check_sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    for check in invoice.checks or []:
        check_sheet.append(
            [
                check.get("code", ""),
                check.get("severity", ""),
                check.get("field", ""),
                check.get("line_position", ""),
                check.get("message", ""),
                check.get("expected", ""),
                check.get("actual", ""),
                check.get("difference", ""),
            ]
        )
    for column, width in zip("ABCDEFGH", [24, 12, 20, 8, 75, 14, 14, 14]):
        check_sheet.column_dimensions[column].width = width
    for row in check_sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    workbook.save(target)


def _write_report(invoice: Invoice, target: Path) -> None:
    extracted = invoice.totals_extracted or {}
    calculated = invoice.totals_calculated or {}
    lines = [
        f"RAPPORT DE CONTRÔLE - FACTURE INTERNE {invoice.id}",
        "=" * 60,
        f"Fournisseur : {invoice.supplier.name if invoice.supplier else invoice.supplier_name_raw or 'inconnu'}",
        f"N° facture : {invoice.invoice_number or 'inconnu'}",
        f"Date facture : {_date_fr(invoice.invoice_date)}",
        "",
        "TOTAUX",
        "-" * 60,
        f"{'':32}{'Extrait':>14}{'Recalculé':>14}",
        f"{'Total HT':32}{_decimal_csv(_to_decimal(extracted.get('total_ht'))):>14}{_decimal_csv(_to_decimal(calculated.get('total_ht'))):>14}",
        f"{'TVA':32}{_decimal_csv(_to_decimal(extracted.get('vat_total'))):>14}{_decimal_csv(_to_decimal(calculated.get('vat_total'))):>14}",
        f"{'Timbre':32}{_decimal_csv(_to_decimal(extracted.get('timbre'))):>14}{_decimal_csv(_to_decimal(calculated.get('timbre'))):>14}",
        f"{'Total TTC':32}{_decimal_csv(_to_decimal(extracted.get('total_ttc'))):>14}{_decimal_csv(_to_decimal(calculated.get('total_ttc'))):>14}",
        "",
        "CONTRÔLES",
        "-" * 60,
    ]
    for check in invoice.checks or []:
        lines.append(f"[{check.get('severity', '').upper()}] {check.get('code', '')} - {check.get('message', '')}")
        if check.get("difference"):
            lines.append(
                f"    attendu={check.get('expected', '')} réel={check.get('actual', '')} écart={check.get('difference')}"
            )
    lines.extend(["", TULIP_WARNING, ""])
    target.write_text("\n".join(lines), encoding="utf-8")


def export_invoice(db: Session, invoice: Invoice, formats: list[str], actor: str = "utilisateur") -> list[ExportRecord]:
    if invoice.status not in {"VALIDEE", "EXPORTEE"}:
        raise ExportError("La facture doit être validée avant tout export.")
    allowed = {"csv", "xlsx", "json", "rapport"}
    formats = [item.lower() for item in formats if item.lower() in allowed]
    if not formats:
        formats = ["csv", "xlsx", "json", "rapport"]
    directory = _export_directory(invoice)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = _safe_stem(invoice)
    records: list[ExportRecord] = []
    already_exported = invoice.status == "EXPORTEE"

    for export_format in formats:
        target = directory / f"{stem}-{timestamp}.{export_format}"
        if export_format == "csv":
            _write_csv(invoice, target)
        elif export_format == "xlsx":
            _write_xlsx(invoice, target)
        elif export_format == "json":
            payload = invoice_payload(invoice)
            payload["export"] = {
                "format": "json-normalise",
                "genere_le": datetime.now(timezone.utc).isoformat(),
                "avertissement_tulip": TULIP_WARNING,
            }
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        elif export_format == "rapport":
            _write_report(invoice, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        record = ExportRecord(
            invoice_id=invoice.id,
            format=export_format,
            file_path=target.relative_to(settings.data_dir).as_posix(),
            sha256=digest,
            mode="export_fichier",
            status="GENERE",
            note="Réexportation d'une facture déjà exportée." if already_exported else None,
        )
        db.add(record)
        records.append(record)

    invoice.status = "EXPORTEE"
    invoice.exported_at = datetime.now(timezone.utc)
    record_audit(
        db,
        invoice.id,
        "export",
        actor=actor,
        details={"formats": formats, "records": len(records), "reexport": already_exported},
    )
    db.commit()
    for record in records:
        db.refresh(record)
    return records
