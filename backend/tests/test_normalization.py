from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.normalization import (
    format_money_fr,
    name_key,
    normalize_invoice_number,
    parse_date,
    parse_decimal,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234,50", Decimal("1234.50")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("1234,5", Decimal("1234.5")),
        ("12 000", Decimal("12000")),
        ("0,00", Decimal("0.00")),
        ("-45,10", Decimal("-45.10")),
        ("(45,10)", Decimal("-45.10")),
        ("450,00 DA", Decimal("450.00")),
        ("19%", Decimal("19")),
        ("", None),
        ("abc", None),
    ],
)
def test_parse_decimal(raw, expected):
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12/03/2026", date(2026, 3, 12)),
        ("12-03-2026", date(2026, 3, 12)),
        ("2026-03-12", date(2026, 3, 12)),
        ("12.03.26", date(2026, 3, 12)),
        ("31/02/2026", None),
        ("", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_name_key_ignores_legal_suffixes_and_accents():
    assert name_key("Établissement SAHARA Distribution SARL") == "sahara distribution"


def test_invoice_number_normalization():
    assert normalize_invoice_number("FA 2026/0042") == "FA20260042"


def test_french_money_format():
    assert format_money_fr(Decimal("1234.5")) == "1\u00a0234,50 DZD"
