from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...models import Invoice, InvoiceLine
from ...normalization import parse_date, to_jsonable
from ..matching.products import match_lines
from ..matching.suppliers import find_supplier_candidates
from ..ocr.base import OcrLine
from ..validation import recompute_invoice
from .llm import extractor as llm_extractor
from .llm import merge_llm_result
from .rules import parse_invoice

SOURCE_IA = "analyse IA"
CONFIDENCE_IA = 0.7

HEADER_FIELDS = (
    "supplier_name_raw",
    "invoice_number",
    "invoice_date",
    "bc_number",
    "bc_date",
    "bl_number",
    "bl_date",
    "document_type",
    "currency",
)
TOTAL_FIELDS = ("total_ht", "discount_total", "vat_total", "timbre", "other_taxes", "total_ttc")


def _invoice_text(invoice: Invoice) -> str:
    if (invoice.raw_text or "").strip():
        return invoice.raw_text or ""
    return "\n".join((page.text or "") for page in invoice.pages).strip()


def _lines_for_rules(text: str) -> list[OcrLine]:
    return [
        OcrLine(text=line, page_number=1, bbox={"y0": float(index)})
        for index, line in enumerate((text or "").splitlines())
        if line.strip()
    ]


def _proposal_entry(current: Any, proposed: Any, value: Any | None = None) -> dict[str, Any] | None:
    if proposed in (None, ""):
        return None
    proposed_val = value if value is not None else proposed
    status = "fill" if current in (None, "") else ("confirm" if current != proposed_val else "same")
    if status == "same":
        return None
    return {"current": to_jsonable(current), "proposed": proposed_val, "status": status}


def _re_extract(invoice: Invoice) -> tuple[Any, str, bool]:
    text = _invoice_text(invoice)
    extracted = parse_invoice(_lines_for_rules(text))
    llm_used = False
    if llm_extractor.available and text.strip():
        llm_result = llm_extractor.extract(text)
        if llm_result is not None:
            extracted = merge_llm_result(extracted, llm_result)
            llm_used = True
    return extracted, text, llm_used


def analyze_invoice(db: Session, invoice: Invoice) -> dict[str, Any]:
    extracted, text, llm_used = _re_extract(invoice)

    header: dict[str, Any] = {}
    for field_name in HEADER_FIELDS:
        proposed = to_jsonable(getattr(extracted, field_name))
        current = to_jsonable(getattr(invoice, field_name))
        entry = _proposal_entry(current, proposed)
        if entry:
            header[field_name] = entry

    current_totals = dict(invoice.totals_extracted or {})
    totals: dict[str, Any] = {}
    for field_name in TOTAL_FIELDS:
        proposed = extracted.totals.get(field_name)
        if proposed is None:
            continue
        entry = _proposal_entry(to_jsonable(current_totals.get(field_name)), str(proposed))
        if entry:
            totals[field_name] = entry

    lines = [
        {
            "raw_reference": item.raw_reference,
            "raw_designation": item.designation[:255],
            "lot_number": item.lot_number,
            "packages": to_jsonable(item.packages),
            "quantity": to_jsonable(item.quantity),
            "unit_price_ht": to_jsonable(item.unit_price_ht),
            "vat_rate": to_jsonable(item.vat_rate),
            "line_total_ht": to_jsonable(item.line_total_ht),
            "discount_value": to_jsonable(item.discount_value),
            "discount_type": item.discount_type,
        }
        for item in extracted.lines
    ]

    return {
        "llm_available": llm_extractor.available,
        "llm_used": llm_used,
        "text_length": len(text or ""),
        "proposal": {"header": header, "totals": totals, "lines": lines},
        "supplier_candidates": find_supplier_candidates(
            db, extracted.supplier_name_raw, extracted.supplier_candidates
        ),
    }


def apply_proposal(db: Session, invoice: Invoice, analysis: dict[str, Any], actor: str = "ia") -> dict[str, Any]:
    proposal = analysis.get("proposal", {})
    changes: dict[str, Any] = {"header": {}, "totals": {}, "lines": 0, "supplier": None}

    header_raw = dict(invoice.header_raw or {})
    for field_name, entry in proposal.get("header", {}).items():
        current = getattr(invoice, field_name)
        if current not in (None, ""):
            continue
        value = entry["proposed"]
        if field_name in {"bc_date", "bl_date", "invoice_date"}:
            value = parse_date(str(value))
            if value is None:
                continue
        else:
            value = str(value)
        setattr(invoice, field_name, value)
        header_raw[field_name] = {"value": CONFIDENCE_IA, "source": SOURCE_IA}
        changes["header"][field_name] = to_jsonable(value)
    invoice.header_raw = header_raw

    if proposal.get("totals"):
        totals = dict(invoice.totals_extracted or {})
        confidence = dict(totals.get("confidence") or {})
        raw_values = dict(totals.get("raw") or {})
        for field_name, entry in proposal["totals"].items():
            current = to_jsonable(totals.get(field_name))
            if current in (None, "") and entry["proposed"] not in (None, ""):
                totals[field_name] = str(entry["proposed"])
                confidence[field_name] = CONFIDENCE_IA
                raw_values[field_name] = str(entry["proposed"])
                changes["totals"][field_name] = entry["proposed"]
        totals["confidence"] = confidence
        totals["raw"] = raw_values
        invoice.totals_extracted = totals

    if not invoice.lines and proposal.get("lines"):
        for position, item in enumerate(proposal["lines"], start=1):
            invoice.lines.append(
                InvoiceLine(
                    position=position,
                    raw_reference=item.get("raw_reference"),
                    raw_designation=item.get("raw_designation") or "ligne IA",
                    lot_number=item.get("lot_number"),
                    packages=item.get("packages"),
                    quantity=item.get("quantity"),
                    unit_price_ht=item.get("unit_price_ht"),
                    vat_rate=item.get("vat_rate"),
                    line_total_ht_extracted=item.get("line_total_ht"),
                    discount_value=item.get("discount_value"),
                    discount_type=item.get("discount_type"),
                    confidence={"global": CONFIDENCE_IA, "source": SOURCE_IA},
                    original_values={"source": SOURCE_IA},
                )
            )
        changes["lines"] = len(proposal["lines"])

    supplier_changes = None
    if invoice.supplier_id is None:
        best = analysis.get("supplier_candidates") or []
        candidate = best[0] if best and float(best[0].get("score") or 0) >= 0.9 else None
        if candidate:
            invoice.supplier_id = candidate["supplier_id"]
            invoice.supplier_code_snapshot = candidate.get("code")
            invoice.supplier_match = {
                "candidates": best,
                "score": candidate["score"],
                "method": candidate.get("method"),
                "confirmed": False,
            }
            invoice.supplier_name_raw = invoice.supplier_name_raw or candidate.get("name")
            supplier_changes = {"supplier_id": candidate["supplier_id"], "score": candidate["score"]}
            changes["supplier"] = supplier_changes
            match_lines(db, invoice)

    if changes["header"] or changes["totals"] or changes["lines"] or changes["supplier"]:
        recompute_invoice(invoice)
        from ..audit import record_audit

        record_audit(db, invoice.id, "analyse_ia_appliquee", actor=actor, details={"changes": to_jsonable(changes)})

    return changes
