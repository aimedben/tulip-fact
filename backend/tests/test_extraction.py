from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.extraction.rules import parse_invoice
from app.services.ocr.base import OcrLine

SAMPLE_TEXT = """ETS SAHARA DISTRIBUTION SARL
Zone Industrielle, Lot 12, Alger
NIF: 000216001234567   RC: 16/00-1234567 B 21
Tel: 021 55 44 33

FACTURE
N° Facture: FA-2026-0042
Date facture: 12/03/2026
N° BC: BC-2026-118
Date BC: 02/03/2026
N° BL: BL-2026-090
Date BL: 10/03/2026
Devise: DZD

Réf.   Désignation                         Lot        Colis  Qté   PU HT    TVA   Montant HT
ART-001 CAFE MOULU 500G                  LOT-A17      2     24    450,00   19    10 800,00
ART-002 THE VERT 200G                    LOT-B04      1     12    320,50   19     3 846,00
ART-003 SUCRE BLANC 1KG                  LOT-C09      3     36    120,00   19     4 320,00

Total HT: 18 966,00
Remise: 0,00
TVA 19%: 3 603,54
Timbre: 0,00
Total TTC: 22 569,54
"""


def _lines(text: str) -> list[OcrLine]:
    return [OcrLine(text=line, page_number=1, bbox={"x0": 0.1, "y0": i / 100, "x1": 0.9, "y1": (i + 1) / 100}) for i, line in enumerate(text.splitlines())]


def test_header_and_lines_extraction():
    invoice = parse_invoice(_lines(SAMPLE_TEXT))
    assert invoice.invoice_number == "FA-2026-0042"
    assert invoice.invoice_date == date(2026, 3, 12)
    assert invoice.bc_number == "BC-2026-118"
    assert invoice.bc_date == date(2026, 3, 2)
    assert invoice.bl_number == "BL-2026-090"
    assert invoice.bl_date == date(2026, 3, 10)
    assert invoice.document_type == "FACTURE"
    assert invoice.bl_facture is None
    assert invoice.currency == "DZD"
    assert invoice.supplier_name_raw == "ETS SAHARA DISTRIBUTION SARL"
    assert len(invoice.lines) == 3
    first = invoice.lines[0]
    assert first.raw_reference == "ART-001"
    assert first.designation == "CAFE MOULU 500G"
    assert first.lot_number == "A17"
    assert first.packages == Decimal("2")
    assert first.quantity == Decimal("24")
    assert first.unit_price_ht == Decimal("450.00")
    assert first.vat_rate == Decimal("19")
    assert first.line_total_ht == Decimal("10800.00")
    assert first.confidence["coherent"] is True


def test_totals_extraction():
    invoice = parse_invoice(_lines(SAMPLE_TEXT))
    assert invoice.totals["total_ht"] == Decimal("18966.00")
    assert invoice.totals["vat_total"] == Decimal("3603.54")
    assert invoice.totals["timbre"] == Decimal("0.00")
    assert invoice.totals["total_ttc"] == Decimal("22569.54")
    assert invoice.totals["vat_breakdown"] == {"19": "3603.54"}


def test_missing_fields_are_not_invented():
    text = "FACTURE\nDate facture: 12/03/2026\nArticle divers 2 100,00 19 200,00"
    invoice = parse_invoice(_lines(text))
    assert invoice.invoice_number is None
    assert invoice.bc_number is None
    assert invoice.bl_date is None
    assert invoice.bl_facture is None
    assert any(w["code"] == "NUMERO_FACTURE_ABSENT" for w in invoice.warnings)
    assert len(invoice.lines) == 1
    assert invoice.lines[0].lot_number is None


def test_continuation_line_is_appended():
    text = """FACTURE
N° Facture: FA-1
Date facture: 01/01/2026
ART-001 CAFE SPECIAL 2 100,00 19 200,00
MOULU EXTRA FIN
Total HT: 200,00
Total TTC: 238,00
"""
    invoice = parse_invoice(_lines(text))
    assert len(invoice.lines) == 1
    assert "MOULU EXTRA FIN" in invoice.lines[0].designation
    assert invoice.lines[0].confidence["designation"] < 0.75
