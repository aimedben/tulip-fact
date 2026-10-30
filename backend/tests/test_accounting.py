from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.accounting import compute_line, verify_invoice


def line(**kwargs):
    defaults = {
        "position": 1,
        "quantity": Decimal("2"),
        "unit_price_ht": Decimal("100"),
        "vat_rate": Decimal("19"),
        "line_total_ht_extracted": Decimal("200"),
        "discount_value": None,
        "discount_type": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def invoice(lines, totals):
    return SimpleNamespace(lines=lines, totals_extracted=totals)


def test_line_computation_with_percent_discount():
    result = compute_line(line(quantity=Decimal("10"), unit_price_ht=Decimal("50"), discount_value=Decimal("10"), discount_type="percent"))
    assert result["gross"] == Decimal("500.00")
    assert result["discount"] == Decimal("50.00")
    assert result["net"] == Decimal("450.00")


def test_consistent_invoice_has_no_error():
    inv = invoice(
        [line(), line(position=2, quantity=Decimal("1"), unit_price_ht=Decimal("50"), line_total_ht_extracted=Decimal("50"), vat_rate=Decimal("9"))],
        {"total_ht": "250.00", "vat_total": "42.50", "timbre": "0", "total_ttc": "292.50"},
    )
    totals, checks = verify_invoice(inv)
    assert totals["total_ht"] == Decimal("250.00")
    assert totals["vat_breakdown"] == {"19": Decimal("38.00"), "9": Decimal("4.50")}
    assert totals["total_ttc"] == Decimal("292.50")
    assert [check for check in checks if check["severity"] == "error"] == []


def test_line_mismatch_is_flagged_without_auto_correction():
    inv = invoice(
        [line(line_total_ht_extracted=Decimal("150"))],
        {"total_ht": "150.00", "vat_total": "28.50", "total_ttc": "178.50"},
    )
    totals, checks = verify_invoice(inv)
    codes = {check["code"] for check in checks}
    assert "LIGNE_MONTANT_ECART" in codes
    assert totals["total_ht"] == Decimal("200.00")
    assert inv.lines[0].line_total_ht_extracted == Decimal("150")


def test_vat_and_ttc_mismatch_identifies_source():
    inv = invoice(
        [line()],
        {"total_ht": "200.00", "vat_total": "30.00", "total_ttc": "230.00"},
    )
    _, checks = verify_invoice(inv)
    ttc = next(check for check in checks if check["code"] == "TOTAL_TTC_ECART")
    assert ttc["source"] == "TVA"


def test_timbre_and_other_taxes_are_added_to_ttc():
    inv = invoice(
        [line()],
        {"total_ht": "200.00", "vat_total": "38.00", "timbre": "5.00", "other_taxes": "2.00", "total_ttc": "245.00"},
    )
    totals, checks = verify_invoice(inv)
    assert totals["total_ttc"] == Decimal("245.00")
    assert [check for check in checks if check["severity"] == "error"] == []


def test_tolerance_allows_rounding_but_not_large_gap():
    inv = invoice(
        [line(line_total_ht_extracted=Decimal("200.04"))],
        {"total_ht": "200.04", "vat_total": "38.008", "total_ttc": "238.05"},
    )
    _, checks = verify_invoice(inv, tolerance=Decimal("0.10"))
    assert [check for check in checks if check["severity"] == "error"] == []
    _, strict_checks = verify_invoice(inv, tolerance=Decimal("0.01"))
    assert any(check["code"] == "LIGNE_MONTANT_ECART" for check in strict_checks)


def test_missing_totals_are_warnings_not_errors():
    inv = invoice([line()], {})
    _, checks = verify_invoice(inv)
    assert any(check["code"] == "TOTAL_HT_NON_EXTRAIT" for check in checks)
    assert not any(check["severity"] == "error" for check in checks)
