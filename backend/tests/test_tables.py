from decimal import Decimal

from app.services.extraction.rules import parse_invoice
from app.services.extraction.tables import parse_table_rows
from app.services.ocr.base import OcrLine


def _word(text: str, x0: float, x1: float, y: float) -> dict:
    return {"text": text, "x0": x0, "x1": x1, "y0": y, "y1": y + 0.02}


def _row(y: float, words: list[tuple[str, float, float]]) -> OcrLine:
    items = [_word(text, x0, x1, y) for text, x0, x1 in words]
    return OcrLine(
        text=" ".join(text for text, _, _ in words),
        page_number=1,
        bbox={"x0": min(item["x0"] for item in items), "y0": y, "x1": max(item["x1"] for item in items), "y1": y + 0.02},
        words=items,
        confidence=0.9,
    )


HEADER = _row(
    0.37,
    [("Produit", 0.07, 0.18), ("Qnt", 0.47, 0.52), ("Prix", 0.61, 0.66), ("Total", 0.76, 0.83)],
)

FACTURE_336 = [
    HEADER,
    _row(
        0.41,
        [("Delicia", 0.07, 0.14), ("480", 0.16, 0.19), ("gr", 0.20, 0.24), ("4X1", 0.47, 0.52), ("26500", 0.62, 0.69), ("1060.00", 0.78, 0.87)],
    ),
    _row(
        0.54,
        [("Pate", 0.01, 0.06), ("fromage", 0.07, 0.16), ("2", 0.17, 0.18), ("kg", 0.19, 0.22), ("6.091X1", 0.46, 0.53), ("340,00", 0.61, 0.67), ("207094", 0.78, 0.87)],
    ),
    _row(
        0.56,
        [("Delicis", 0.10, 0.19), ("1,5", 0.20, 0.24), ("kg", 0.25, 0.29), ("2.996X1", 0.46, 0.53), ("55000", 0.61, 0.68), ("164780", 0.78, 0.88)],
    ),
    _row(0.71, [("Total", 0.08, 0.13), ("Payé", 0.14, 0.20), ("11", 0.80, 0.82), ("320,36", 0.83, 0.90)]),
]


def test_colisage_quantity_is_the_printed_one():
    lines = parse_table_rows(FACTURE_336)
    assert lines is not None
    quantities = [line.quantity for line in lines]
    assert Decimal("4") in quantities
    assert Decimal("6.091") in quantities
    assert Decimal("2.996") in quantities


def test_lost_decimal_separator_is_repaired():
    lines = parse_invoice(FACTURE_336).lines
    delicia = next(line for line in lines if line.designation.startswith("Delicia 480"))
    assert delicia.unit_price_ht == Decimal("265.00")
    assert delicia.line_total_ht == Decimal("1060.00")

    pate = next(line for line in lines if line.designation.startswith("Pate fromage 2"))
    assert pate.unit_price_ht == Decimal("340.00")
    assert pate.line_total_ht == Decimal("2070.94")

    delicia_15 = next(line for line in lines if line.designation.startswith("Delicis 1,5"))
    assert delicia_15.unit_price_ht == Decimal("550.00")
    assert delicia_15.line_total_ht == Decimal("1647.80")


def test_totals_line_is_not_an_article():
    lines = parse_table_rows(FACTURE_336) or []
    assert all("Total" not in (line.designation or "") for line in lines)


def test_parse_invoice_uses_table_columns():
    invoice = parse_invoice(FACTURE_336)
    assert invoice.meta.get("table_parsing") is True
    delicia = next(line for line in invoice.lines if line.designation.startswith("Delicia 480"))
    assert delicia.quantity == Decimal("4")
    assert delicia.unit_price_ht == Decimal("265.00")
