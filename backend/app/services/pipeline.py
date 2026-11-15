from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .. import database
from ..config import settings
from ..models import Invoice, InvoiceLine, InvoicePage
from ..normalization import to_jsonable
from .accounting import compute_line, verify_invoice
from .audit import record_audit
from .duplicates import detect_duplicates, duplicate_warning
from .extraction.llm import extractor as llm_extractor  # noqa: F401
from .extraction.vision import cooldown_status, extractor as vision_extractor
from .extraction.llm import merge_llm_result
from .extraction.regions import recover_designation
from .extraction.rules import parse_invoice
from .matching.products import match_lines
from .matching.suppliers import find_supplier_candidates
from .ocr import OcrError, process_document
from .storage import delete_invoice_files, pages_dir_for, pages_prefix_for

logger = logging.getLogger(__name__)

MATCHED_STATUSES = {"RAPPROCHE", "CONFIRME"}
REPROCESS_METHODS = {"auto", "ocr", "gemini", "chatgpt", "nemotron"}
VISION_METHODS = {"gemini", "chatgpt", "nemotron"}


class Pipeline:
    def __init__(self, invoice_id: int, session_factory=None, method: str = "auto"):
        self.invoice_id = invoice_id
        self.session_factory = session_factory or database.SessionLocal
        self.method = method if method in REPROCESS_METHODS else "auto"
        self.db = self.session_factory()
        self.invoice: Invoice | None = None

    def close(self) -> None:
        self.db.close()

    def _set_progress(self, stage: str, progress: int, status: str | None = None) -> None:
        assert self.invoice is not None
        self.invoice.stage = stage
        self.invoice.progress = max(0, min(100, progress))
        if status:
            self.invoice.status = status
        self.db.commit()

    def _ocr_progress(self, current: int, total: int, label: str) -> None:
        ratio = current / max(total, 1)
        progress = 15 + int(ratio * 45)
        self._set_progress(f"OCR page {current}/{total} ({label})", progress, "EXTRACTION")

    def run(self) -> bool:
        try:
            return self._run()
        except Exception as exc:
            self.db.rollback()
            logger.error("Échec du traitement de la facture %s : %s", self.invoice_id, type(exc).__name__)
            return self._mark_failure(exc)
        finally:
            self.close()

    def _mark_failure(self, exc: Exception) -> bool:
        try:
            invoice = self.db.get(Invoice, self.invoice_id)
            if invoice is None:
                return False
            invoice.status = "ECHEC"
            invoice.stage = "échec"
            invoice.progress = 100
            if isinstance(exc, OcrError):
                invoice.error_message = str(exc)[:1000]
            else:
                invoice.error_message = (
                    "Le traitement a échoué. Consultez le journal technique et relancez le traitement."
                )
            record_audit(
                self.db,
                invoice.id,
                "echec_traitement",
                details={"error_type": type(exc).__name__, "error": invoice.error_message},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
        return False

    def _run(self) -> bool:
        invoice = self.db.get(Invoice, self.invoice_id)
        if invoice is None:
            return False
        self.invoice = invoice
        invoice.status = "EXTRACTION"
        invoice.stage = "préparation du document"
        invoice.progress = 8
        invoice.error_message = None
        self.db.commit()

        document_path = Path(settings.data_dir) / invoice.stored_path
        if not document_path.is_file():
            raise OcrError("Le fichier original est introuvable dans le stockage local.")

        delete_invoice_files(invoice.uuid)
        page_directory = pages_dir_for(invoice.uuid)
        prefix = pages_prefix_for(invoice.uuid)
        document = process_document(document_path, page_directory, prefix, progress=self._ocr_progress)

        invoice.pages.clear()
        self.db.flush()
        for page in document.pages:
            invoice.pages.append(
                InvoicePage(
                    page_number=page.page_number,
                    image_path=page.image_path,
                    text=page.text,
                    ocr_engine=page.engine,
                    rotation=page.rotation,
                    width=page.width or None,
                    height=page.height or None,
                    confidence=Decimal(str(page.confidence)) if page.confidence is not None else None,
                )
            )
        invoice.page_count = len(document.pages)
        invoice.raw_text = document.text
        invoice.document_meta = to_jsonable(document.meta)
        self._set_progress("extraction structurée", 62, "EXTRACTION")

        extracted = parse_invoice(document.all_lines)
        extracted.meta["analysis_method"] = self.method
        for ocr_warning in document.meta.get("ocr_warnings") or []:
            if isinstance(ocr_warning, dict):
                extracted.warnings = [*extracted.warnings, ocr_warning]
        page_paths = [(Path(settings.data_dir) / page.image_path) for page in document.pages]

        if self.method in VISION_METHODS:
            provider = "opencode" if self.method == "nemotron" else self.method
            if not vision_extractor.available_for(provider):
                extracted.warnings = [
                    *extracted.warnings,
                    {
                        "code": "VISION_INDISPONIBLE",
                        "severity": "warning",
                        "message": f"Le fournisseur {self.method} n'est pas configuré ; le résultat OCR local est conservé.",
                    },
                ]
            else:
                self._set_progress(f"lecture IA des images ({self.method})", 64, "EXTRACTION")
                vision_result = vision_extractor.extract(
                    page_paths,
                    ocr_text=document.text,
                    provider=provider,
                    force=True,
                )
                if vision_result is not None:
                    replace_lines = not extracted.meta.get("table_parsing")
                    extracted = merge_llm_result(extracted, vision_result, replace_lines=replace_lines)
                    extracted.meta["vision_used"] = True
                else:
                    in_cooldown, reason = cooldown_status(provider)
                    message = reason or (
                        f"L'analyse {self.method} n'a pas répondu ; le résultat OCR local est conservé."
                    )
                    extracted.warnings = [
                        *extracted.warnings,
                        {
                            "code": "VISION_INDISPONIBLE",
                            "severity": "warning",
                            "message": message,
                        },
                    ]
        elif self.method == "auto":
            if vision_extractor.available:
                self._set_progress("lecture IA des images", 64, "EXTRACTION")
                vision_result = vision_extractor.extract(page_paths, ocr_text=document.text)
                if vision_result is not None:
                    replace_lines = not extracted.meta.get("table_parsing")
                    extracted = merge_llm_result(extracted, vision_result, replace_lines=replace_lines)
                    extracted.meta["vision_used"] = True
                else:
                    in_cooldown, reason = cooldown_status()
                    if in_cooldown:
                        extracted.warnings = [
                            *extracted.warnings,
                            {
                                "code": "VISION_INDISPONIBLE",
                                "severity": "warning",
                                "message": reason,
                            },
                        ]
            if llm_extractor.available:
                self._set_progress("complement IA texte", 67, "EXTRACTION")
                llm_result = llm_extractor.extract(document.text)
                if llm_result is not None:
                    extracted = merge_llm_result(extracted, llm_result)

        if extracted.meta:
            merged_meta = to_jsonable(document.meta)
            if isinstance(merged_meta, dict):
                for key, value in extracted.meta.items():
                    merged_meta.setdefault(key, value)
                invoice.document_meta = merged_meta

        for line in extracted.lines:
            if (line.designation or "").strip().lower() in {"", "article à compléter", "article a completer"}:
                page_index = (line.source_page or 1) - 1
                if 0 <= page_index < len(document.pages):
                    recovered = recover_designation(
                        Path(settings.data_dir) / document.pages[page_index].image_path,
                        line.source_bbox,
                    )
                    if recovered:
                        line.designation = recovered
                        line.confidence["designation"] = 0.7
            quantity = line.quantity
            unit_price = line.unit_price_ht
            total = line.line_total_ht
            if quantity and unit_price and total:
                tolerance = max(Decimal("0.05"), abs(total) * Decimal("0.002"))
                if abs(quantity * unit_price - total) > tolerance:
                    # Règle n°1: ne JAMAIS corriger silencieusement les valeurs
                    # Ajouter seulement un warning visible pour l'utilisateur
                    if "LIGNE_CALCUL_INCOHERENT" not in [w.get("code") for w in line.confidence.get("_warnings", [])]:
                        if not hasattr(line, '_original_warnings'):
                            line._original_warnings = list(line.confidence.get("_warnings", []))
                        line.confidence.setdefault("_warnings", []).append({
                            "code": "LIGNE_CALCUL_INCOHERENT",
                            "severity": "warning",
                            "message": f"Calcul incohérent: {quantity} × {unit_price} ≠ {total}",
                        })

        invoice.supplier_name_raw = extracted.supplier_name_raw
        invoice.invoice_number = extracted.invoice_number
        invoice.invoice_date = extracted.invoice_date
        invoice.bc_number = extracted.bc_number
        invoice.bc_date = extracted.bc_date
        invoice.bl_number = extracted.bl_number
        invoice.bl_date = extracted.bl_date
        invoice.document_type = extracted.document_type
        invoice.bl_facture = extracted.bl_facture
        invoice.currency = extracted.currency or "DZD"
        invoice.header_raw = to_jsonable(extracted.header_raw)
        invoice.totals_extracted = to_jsonable(extracted.totals)
        invoice.warnings = to_jsonable(extracted.warnings)
        self._set_progress("recherche du fournisseur", 70)

        candidates = find_supplier_candidates(
            self.db,
            extracted.supplier_name_raw,
            extracted.supplier_candidates,
        )
        auto = next((candidate for candidate in candidates if candidate.get("auto")), None)
        selected = auto or (candidates[0] if candidates and candidates[0]["score"] >= 0.98 else None)
        if selected:
            invoice.supplier_id = selected["supplier_id"]
            invoice.supplier_code_snapshot = selected["code"]
            invoice.supplier_name_raw = invoice.supplier_name_raw or selected["name"]
            invoice.supplier_match = {
                "candidates": candidates,
                "score": selected["score"],
                "method": selected["method"],
                "confirmed": True if selected.get("auto") else False,
            }
        else:
            invoice.supplier_id = None
            invoice.supplier_code_snapshot = None
            invoice.supplier_match = {"candidates": candidates, "confirmed": False}
            if candidates:
                invoice.warnings = list(invoice.warnings) + [
                    {
                        "code": "FOURNISSEUR_A_CONFIRMER",
                        "severity": "warning",
                        "message": "Aucune correspondance exacte de fournisseur. Confirmez le fournisseur parmi les suggestions.",
                        "field": "supplier_id",
                    }
                ]
        self.db.flush()

        invoice.lines.clear()
        self.db.flush()
        for position, extracted_line in enumerate(extracted.lines, start=1):
            line = InvoiceLine(
                position=position,
                raw_reference=extracted_line.raw_reference,
                raw_designation=extracted_line.designation[:255],
                lot_number=extracted_line.lot_number,
                packages=extracted_line.packages,
                quantity=extracted_line.quantity,
                unit_price_ht=extracted_line.unit_price_ht,
                vat_rate=extracted_line.vat_rate,
                line_total_ht_extracted=extracted_line.line_total_ht,
                discount_value=extracted_line.discount_value,
                discount_type=extracted_line.discount_type,
                confidence=to_jsonable(extracted_line.confidence),
                source_page=extracted_line.source_page,
                source_bbox=extracted_line.source_bbox,
                original_values=to_jsonable(
                    {
                        "raw_text": extracted_line.original_text,
                        "reference": extracted_line.raw_reference,
                        "designation": extracted_line.designation,
                        "quantity": extracted_line.quantity,
                        "unit_price_ht": extracted_line.unit_price_ht,
                        "vat_rate": extracted_line.vat_rate,
                        "line_total_ht": extracted_line.line_total_ht,
                        "lot_number": extracted_line.lot_number,
                        "packages": extracted_line.packages,
                    }
                ),
            )
            invoice.lines.append(line)
        self._set_progress("rapprochement des articles", 82)

        match_lines(self.db, invoice)
        self._set_progress("contrôle des doublons", 88)
        _, _, _, duplicate_reasons = detect_duplicates(self.db, invoice)
        if duplicate_reasons:
            invoice.warnings = list(invoice.warnings) + duplicate_warning(duplicate_reasons)
            invoice.document_meta = {**invoice.document_meta, "duplicate_reasons": duplicate_reasons}

        totals_calculated, checks = verify_invoice(invoice, tolerance=settings.amount_tolerance)
        invoice.totals_calculated = to_jsonable(totals_calculated)
        invoice.checks = to_jsonable(checks)
        for index, line in enumerate(invoice.lines, start=1):
            line.line_total_ht_calculated = compute_line(line)["net"]
            line.position = line.position or index

        all_matched = bool(invoice.lines) and all(line.match_status in MATCHED_STATUSES for line in invoice.lines)
        has_accounting_error = any(check.get("severity") == "error" for check in checks)
        has_critical_warning = any(
            warning.get("code") in {"AUCUNE_LIGNE"} for warning in (invoice.warnings or [])
        )
        if (
            invoice.supplier_id is not None
            and invoice.invoice_number
            and invoice.invoice_date is not None
            and all_matched
            and not has_accounting_error
            and not has_critical_warning
            and not invoice.is_duplicate
        ):
            invoice.status = "PRETE_A_VALIDER"
        else:
            invoice.status = "A_VERIFIER"

        invoice.processed_at = datetime.now(timezone.utc)
        invoice.stage = "terminé"
        invoice.progress = 100
        record_audit(
            self.db,
            invoice.id,
            "extraction_terminee",
            details={
                "lines": len(invoice.lines),
                "status": invoice.status,
                "checks": len(checks),
                "ocr": document.meta,
                "duplicate": invoice.is_duplicate,
            },
        )
        self.db.commit()
        return True


def run_pipeline(invoice_id: int, session_factory=None, method: str = "auto") -> bool:
    return Pipeline(invoice_id, session_factory=session_factory, method=method).run()
